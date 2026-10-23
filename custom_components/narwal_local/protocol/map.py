"""StaticMapPayload decoding (from /map/get_map).

Everything on the map is in the border frame, cells of the map's
resolution offset by the map border: col = x - border.left,
row = y - border.bottom.

* Doors, carpets and no-carpet areas are integer cells.
* The dock, the robot pose, furniture, camera-detected objects and no-go
  zones (forbidden areas) are float cells (verified: a double bed lands in
  the bedroom, a toilet in the bathroom, and a no-go zone written this way
  appears where it was drawn; the robot rounds its corners to whole cells).
  Virtual walls go through the same filter in the app, so they are taken to
  be float cells too (not seen on a robot yet).

World metres, the frame of zone cleaning and the position sensor, follow
from origin and resolution: x = originX + col * resolution, likewise y.

Cells and rows are in the stored orientation (row 0 at the bottom); flip
vertically for display.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import gzip
import zlib

from .enums import (
    DirtLabel,
    DirtStatus,
    ForbiddenType,
    FurnitureType,
    ObstacleLabel,
    ServiceResult,
)
from .pb import WIRE_FIXED32, WIRE_VARINT, parse, parse_packed_varints, to_int32

CELL_UNKNOWN = 0
CELL_WALL = 255

# Cell flags: the low byte of each grid value, read off a real map by
# comparing each bit with the app's view. Walls carry 0x28.
FLAG_FREE = 0x01  # floor the robot drives on
FLAG_OBSTACLE_POINT = 0x02  # scattered points: furniture legs and the like
FLAG_CARPET = 0x04  # matches the carpet polygons exactly
FLAG_EDGE = 0x08  # band along walls
FLAG_BLOCKED = 0x10  # area the robot cannot enter; the app shades it darker


@dataclass(slots=True, frozen=True)
class Point:
    """World coordinate in metres (MapBaseType Point{1 x, 2 y}, floats)."""

    x: float
    y: float


@dataclass(slots=True, frozen=True)
class CellPoint:
    """Grid cell coordinate, stored orientation. Fractions are allowed."""

    col: float
    row: float


@dataclass(slots=True, frozen=True)
class CellInt:
    """Integer cell in the border frame (as the robot sends overlays)."""

    x: int
    y: int


@dataclass(slots=True)
class Room:
    id: int  # RoomInfo 1
    name: str = ""  # 3 (customName)
    color: int = 0  # 9


@dataclass(slots=True)
class ForbiddenArea:
    id: int = 0  # 3
    type: ForbiddenType | int = ForbiddenType.UNSPECIFIED  # 2
    mode: int = 0  # 5 (REGION=0, ROOM=1)
    polygon: list[Point] = field(default_factory=list)  # 1, border-frame float cells


@dataclass(slots=True)
class VirtualWall:
    id: int = 0  # 1
    start: Point = Point(0.0, 0.0)  # 2
    end: Point = Point(0.0, 0.0)  # 3


@dataclass(slots=True)
class Polygon:
    """Carpet (field 26) or no-carpet area (field 51) in border-frame cells."""

    id: int = 0
    points: list[CellInt] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class Pose:
    """Position (border-frame float cells) and heading in radians."""

    x: float
    y: float
    theta: float = 0.0


@dataclass(slots=True, frozen=True)
class Furniture:
    """visionData.funitures: furniture placed in the app or recognised.
    (x, y) is the centre; width/height in cells; angle in degrees."""

    id: int
    type: FurnitureType | int
    x: float
    y: float
    width: float
    height: float
    angle: float = 0.0


@dataclass(slots=True, frozen=True)
class Obstacle:
    """visionData.visionObs: an object the camera recognised on the floor."""

    id: int
    label: ObstacleLabel | int
    x: float
    y: float
    task_id: int = 0


@dataclass(slots=True, frozen=True)
class Dirt:
    """visionData.visionDirty: a dirty spot the camera recognised."""

    id: int
    label: DirtLabel | int
    x: float
    y: float
    status: DirtStatus | int = DirtStatus.EXPLORING


@dataclass(slots=True)
class MapInfo:
    result: ServiceResult | int = ServiceResult.UNSPECIFIED
    robot_has_map: bool = False
    map_id: int = 0  # 1
    map_version: int = 0  # 2
    edit_version: int = 0  # 33, bumped by every map edit
    resolution_mm: int = 0  # 3
    width: int = 0  # 4
    height: int = 0  # 5
    origin_x: float = 0.0  # 7
    origin_y: float = 0.0
    border_bottom: int = 0  # 6.1
    border_left: int = 0  # 6.3
    rooms: list[Room] = field(default_factory=list)  # 12
    forbiddens: list[ForbiddenArea] = field(default_factory=list)  # 9
    virtual_walls: list[VirtualWall] = field(default_factory=list)  # 50
    doors: list[list[CellInt]] = field(default_factory=list)  # 11
    carpets: list[Polygon] = field(default_factory=list)  # 26
    no_carpets: list[Polygon] = field(default_factory=list)  # 51
    station: Pose | None = None  # 8
    robot_pose: Pose | None = None  # 24, as of the last map save
    furniture: list[Furniture] = field(default_factory=list)  # 32.1
    obstacles: list[Obstacle] = field(default_factory=list)  # 32.2
    dirt: list[Dirt] = field(default_factory=list)  # 32.3
    map_data_format: int = 0  # 18
    grid_compressed: bytes = b""  # 17
    grid_raw: bytes = b""
    # (grid_raw, width, height, room grid, flag grid); not an init field, so
    # dataclasses.replace() starts a copy with an empty cache.
    _room_grid_cache: tuple | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def resolution_m(self) -> float:
        return self.resolution_mm / 1000.0 if self.resolution_mm else 0.05

    @property
    def ref(self) -> tuple[int, int, int]:
        """(mapId, mapVersion, editVersion); changes whenever the map does."""
        return (self.map_id, self.map_version, self.edit_version)

    def room_name(self, room_id: int) -> str | None:
        return next((r.name for r in self.rooms if r.id == room_id), None)

    # --- coordinates ----------------------------------------------------

    def world_to_cell(self, p: Point) -> CellPoint:
        res = self.resolution_m
        return CellPoint((p.x - self.origin_x) / res, (p.y - self.origin_y) / res)

    def cell_to_world(self, col: float, row: float) -> Point:
        res = self.resolution_m
        return Point(self.origin_x + col * res, self.origin_y + row * res)

    def border_to_cell(self, c: CellInt) -> CellPoint:
        return CellPoint(float(c.x - self.border_left), float(c.y - self.border_bottom))

    def border_point_to_cell(self, x: float, y: float) -> CellPoint:
        """Float border-frame point (dock, furniture, objects) -> display cell."""
        return CellPoint(x - self.border_left, y - self.border_bottom)

    def room_bounds(self) -> dict[int, tuple[float, float, float, float]]:
        """Bounding box of each room in world metres: (x_min, y_min, x_max,
        y_max), the outer edges of its cells."""
        w = self.width
        cells: dict[int, list[int]] = {}
        for i, v in enumerate(self.room_grid()):
            if v in (CELL_UNKNOWN, CELL_WALL):
                continue
            col, row = i % w, i // w
            box = cells.get(v)
            if box is None:
                cells[v] = [col, row, col, row]
            else:
                box[0], box[1] = min(box[0], col), min(box[1], row)
                box[2], box[3] = max(box[2], col), max(box[3], row)
        bounds = {}
        for room_id, (c0, r0, c1, r1) in cells.items():
            lo, hi = self.cell_to_world(c0, r0), self.cell_to_world(c1 + 1, r1 + 1)
            bounds[room_id] = (lo.x, lo.y, hi.x, hi.y)
        return bounds

    def border_to_world(self, x: float, y: float) -> Point:
        """Border-frame point (cells) -> world metres."""
        c = self.border_point_to_cell(x, y)
        return self.cell_to_world(c.col, c.row)

    def world_to_border_point(self, x: float, y: float) -> tuple[float, float]:
        """World metres -> border-frame float cells (no-go zone corners)."""
        c = self.world_to_cell(Point(x, y))
        return c.col + self.border_left, c.row + self.border_bottom

    def world_to_border(self, x: float, y: float) -> tuple[int, int]:
        """World point in metres -> integer border-frame cell (the frame zones
        are sent in)."""
        c = self.world_to_cell(Point(x, y))
        return round(c.col) + self.border_left, round(c.row) + self.border_bottom

    def world_rect_to_grid(self, x1: float, y1: float, x2: float, y2: float) -> tuple[int, int, int, int]:
        """Rectangle between two world corners (metres) in border-frame cells."""
        return (*self.world_to_border(x1, y1), *self.world_to_border(x2, y2))

    def room_at(self, x: float, y: float) -> int | None:
        """Room id under a border-frame point, or None outside any room."""
        c = self.border_point_to_cell(x, y)
        col, row = int(c.col), int(c.row)
        if not (0 <= col < self.width and 0 <= row < self.height):
            return None
        v = self.room_grid()[row * self.width + col]
        return v if v not in (CELL_UNKNOWN, CELL_WALL) else None

    # --- grid -----------------------------------------------------------

    def grid_cells(self) -> list[int]:
        """Raw cell values, row-major, stored orientation. roomId = value >> 8,
        the low byte holds flags, 0 is unknown."""
        buf = self.grid_raw
        if len(buf) > 1 and buf[0] == 0x0A:  # outer {field 1: packed varints}
            for f in parse(buf):
                if f.num == 1:
                    buf = f.data
                    break
        return parse_packed_varints(buf)

    def _decoded_grid(self) -> tuple[bytes, bytes]:
        """(room grid, flag grid), decoded once per grid.

        Decoding the packed grid takes tens of milliseconds, and room_at runs
        once per object for every attribute update, so the result is cached
        for the current grid bytes and size.
        """
        key = (self.grid_raw, self.width, self.height)
        cached = self._room_grid_cache
        if cached is not None and cached[0] is key[0] and cached[1:3] == key[1:]:
            return cached[3], cached[4]
        size = self.width * self.height
        rooms = bytearray(size)
        flags = bytearray(size)
        for i, v in enumerate(self.grid_cells()[:size]):
            if v == 0:
                continue
            room = v >> 8
            rooms[i] = CELL_WALL if room == 0 else room & 0x3F
            flags[i] = v & 0xFF
        result = (bytes(rooms), bytes(flags))
        self._room_grid_cache = (*key, *result)
        return result

    def room_grid(self) -> bytes:
        """One byte per cell: 0 unknown, 255 wall/obstacle, else room id."""
        return self._decoded_grid()[0]

    def flag_grid(self) -> bytes:
        """One byte per cell: the cell's flags (FLAG_* constants), 0 if unknown."""
        return self._decoded_grid()[1]

    def to_json(self) -> dict:
        """Browser/HA-friendly view; matches the Go client's MapJSON."""

        def cp(c: CellPoint) -> dict:
            return {"col": c.col, "row": c.row}

        return {
            "width": self.width,
            "height": self.height,
            "resolutionM": self.resolution_m,
            "originX": self.origin_x,
            "originY": self.origin_y,
            "robotHasMap": self.robot_has_map,
            "rooms": [{"id": r.id, "name": r.name} for r in self.rooms],
            "numCarpets": len(self.carpets),
            "numDoors": len(self.doors),
            "forbiddens": [
                {
                    "id": fa.id,
                    "type": int(fa.type),
                    "polygon": [cp(self.border_point_to_cell(p.x, p.y)) for p in fa.polygon],
                }
                for fa in self.forbiddens
            ],
            "walls": [
                {
                    "id": vw.id,
                    "start": cp(self.border_point_to_cell(vw.start.x, vw.start.y)),
                    "end": cp(self.border_point_to_cell(vw.end.x, vw.end.y)),
                }
                for vw in self.virtual_walls
            ],
            "doors": [[cp(self.border_to_cell(p)) for p in d] for d in self.doors],
            "carpets": [
                {"id": c.id, "polygon": [cp(self.border_to_cell(p)) for p in c.points]}
                for c in self.carpets
            ],
            "noCarpets": [
                {"id": c.id, "polygon": [cp(self.border_to_cell(p)) for p in c.points]}
                for c in self.no_carpets
            ],
            "cellsB64": base64.b64encode(self.room_grid()).decode("ascii"),
        }


# --- decoders ---------------------------------------------------------------


def _point(buf: bytes) -> Point:
    x = y = 0.0
    for f in parse(buf):
        if f.wtype == WIRE_FIXED32:
            if f.num == 1:
                x = f.float
            elif f.num == 2:
                y = f.float
    return Point(x, y)


def _cell_int(buf: bytes) -> CellInt:
    x = y = 0
    for f in parse(buf):
        if f.num == 1:
            x = to_int32(f.int)
        elif f.num == 2:
            y = to_int32(f.int)
    return CellInt(x, y)


def _room(buf: bytes) -> Room:
    room = Room(id=0)
    for f in parse(buf):
        if f.num == 1:
            room.id = f.int
        elif f.num == 3:
            room.name = f.text
        elif f.num == 9:
            room.color = f.int
    return room


def _forbidden(buf: bytes) -> ForbiddenArea:
    fa = ForbiddenArea()
    for f in parse(buf):
        if f.num == 1:
            fa.polygon.append(_point(f.data))
        elif f.num == 2:
            fa.type = ForbiddenType.from_value(f.int)
        elif f.num == 3:
            fa.id = f.int
        elif f.num == 5:
            fa.mode = f.int
    return fa


def _wall(buf: bytes) -> VirtualWall:
    vw = VirtualWall()
    for f in parse(buf):
        if f.num == 1:
            vw.id = f.int
        elif f.num == 2:
            vw.start = _point(f.data)
        elif f.num == 3:
            vw.end = _point(f.data)
    return vw


def _polygon(buf: bytes) -> Polygon:
    poly = Polygon()
    for f in parse(buf):
        if f.num == 1:
            poly.id = f.int
        elif f.num == 2:
            poly.points.append(_cell_int(f.data))
    return poly


def _door(buf: bytes) -> list[CellInt]:
    return [_cell_int(f.data) for f in parse(buf) if f.num == 2]


def _pose(buf: bytes) -> Pose:
    """{1 Point, 2 theta}."""
    x = y = theta = 0.0
    for f in parse(buf):
        if f.num == 1:
            p = _point(f.data)
            x, y = p.x, p.y
        elif f.num == 2 and f.wtype == WIRE_FIXED32:
            theta = f.float
    return Pose(x, y, theta)


def _scalar(f) -> float:
    """Box sizes arrive as floats on the robot; the schema says uint32."""
    return f.float if f.wtype == WIRE_FIXED32 else float(f.int)


def _box(buf: bytes) -> tuple[float, float, float, float]:
    """Box{1 origin Point, 2 width, 3 height} -> (x, y, width, height)."""
    x = y = w = h = 0.0
    for f in parse(buf):
        if f.num == 1:
            p = _point(f.data)
            x, y = p.x, p.y
        elif f.num == 2:
            w = _scalar(f)
        elif f.num == 3:
            h = _scalar(f)
    return x, y, w, h


def _furniture(buf: bytes) -> Furniture:
    fid = ftype = 0
    x = y = w = h = angle = 0.0
    for f in parse(buf):
        if f.num == 1:
            fid = f.int
        elif f.num == 2:
            ftype = f.int
        elif f.num == 3:
            x, y, w, h = _box(f.data)
        elif f.num == 4:
            angle = _scalar(f)
    return Furniture(fid, FurnitureType.from_value(ftype), x, y, w, h, angle)


def _obstacle(buf: bytes) -> Obstacle:
    oid = label = task = 0
    x = y = 0.0
    for f in parse(buf):
        if f.num == 1:
            oid = f.int
        elif f.num == 2:
            label = f.int
        elif f.num == 3:
            x, y, _, _ = _box(f.data)
        elif f.num == 4 and f.wtype == WIRE_VARINT:
            task = f.int
    return Obstacle(oid, ObstacleLabel.from_value(label), x, y, task)


def _dirt(buf: bytes) -> Dirt:
    did = label = status = 0
    x = y = 0.0
    for f in parse(buf):
        if f.num == 1:
            did = f.int
        elif f.num == 2:
            label = f.int
        elif f.num == 3:
            x, y, _, _ = _box(f.data)
        elif f.num == 4:
            status = f.int
    return Dirt(did, DirtLabel.from_value(label), x, y, DirtStatus.from_value(status))


def _vision_data(buf: bytes, mi: MapInfo) -> None:
    """VisionData{1 funitures, 2 visionObs, 3 visionDirty}."""
    for f in parse(buf):
        if f.num == 1:
            mi.furniture.append(_furniture(f.data))
        elif f.num == 2:
            mi.obstacles.append(_obstacle(f.data))
        elif f.num == 3:
            mi.dirt.append(_dirt(f.data))


def _inflate(buf: bytes) -> bytes:
    if buf[:2] == b"\x1f\x8b":
        return gzip.decompress(buf)
    if buf[:1] == b"\x78":
        return zlib.decompress(buf)
    return buf  # already raw


def decode_static_map_payload(payload: bytes) -> MapInfo:
    mi = MapInfo()
    for f in parse(payload):
        match f.num:
            case 1:
                mi.map_id = f.int
            case 2:
                mi.map_version = f.int
            case 3:
                mi.resolution_mm = f.int
            case 4:
                mi.width = f.int
            case 5:
                mi.height = f.int
            case 6:
                for g in parse(f.data):
                    if g.num == 1:
                        mi.border_bottom = to_int32(g.int)
                    elif g.num == 3:
                        mi.border_left = to_int32(g.int)
            case 7:
                origin = _point(f.data)
                mi.origin_x, mi.origin_y = origin.x, origin.y
            case 8:
                mi.station = _pose(f.data)
            case 24:
                mi.robot_pose = _pose(f.data)
            case 32:
                _vision_data(f.data, mi)
            case 9:
                mi.forbiddens.append(_forbidden(f.data))
            case 11:
                mi.doors.append(_door(f.data))
            case 12:
                mi.rooms.append(_room(f.data))
            case 17:
                mi.grid_compressed = f.data
            case 18:
                mi.map_data_format = f.int
            case 26:
                mi.carpets.append(_polygon(f.data))
            case 33:
                mi.edit_version = f.int
            case 50:
                mi.virtual_walls.append(_wall(f.data))
            case 51:
                mi.no_carpets.append(_polygon(f.data))
    if mi.grid_compressed:
        mi.grid_raw = _inflate(mi.grid_compressed)
    return mi


def decode_get_map_response(payload: bytes) -> MapInfo:
    """GetMap_Response{1 result, 2 StaticMapPayload, 3 robotHasMap}."""
    result: ServiceResult | int = ServiceResult.UNSPECIFIED
    has_map = False
    body: bytes | None = None
    for f in parse(payload):
        if f.num == 1:
            result = ServiceResult.from_value(f.int)
        elif f.num == 2:
            body = f.data
        elif f.num == 3:
            has_map = bool(f.int)
    mi = decode_static_map_payload(body) if body is not None else MapInfo()
    mi.result = result
    mi.robot_has_map = has_map
    return mi


@dataclass(slots=True, frozen=True)
class DisplayMap:
    """/map/display_map, pushed about once a second while the robot is active
    (after activate_reporting with a displayMap duration).

    robot (field 1) and dock (field 5) are poses in the same border frame as the
    StaticMapPayload's dock and objects. The push also carries partial map
    updates and the cleaned track, which are not decoded here.
    """

    robot: Pose | None = None
    dock: Pose | None = None
    timestamp_ms: int = 0  # field 10


def decode_display_map(payload: bytes) -> DisplayMap:
    robot = dock = None
    ts = 0
    for f in parse(payload):
        if f.num == 1 and f.wtype != WIRE_VARINT:
            robot = _pose(f.data)
        elif f.num == 5 and f.wtype != WIRE_VARINT:
            dock = _pose(f.data)
        elif f.num == 10 and f.wtype == WIRE_VARINT:
            ts = f.int
    return DisplayMap(robot, dock, ts)
