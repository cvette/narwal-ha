"""StaticMapPayload decoding (from /map/get_map).

Two coordinate systems are in play, both verified on a real robot:

* Forbidden areas and virtual walls are world metres:
  col = (x - originX) / resolution, row = (y - originY) / resolution.
* Doors, carpets and no-carpet areas are integer cells in the border frame:
  col = x - border.left, row = y - border.bottom.

Cells and rows are in the stored orientation (row 0 at the bottom); flip
vertically for display.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import gzip
import zlib

from .enums import ForbiddenType, ServiceResult
from .pb import WIRE_FIXED32, parse, parse_packed_varints, to_int32

CELL_UNKNOWN = 0
CELL_WALL = 255


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
    polygon: list[Point] = field(default_factory=list)  # 1, world metres


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
    map_data_format: int = 0  # 18
    grid_compressed: bytes = b""  # 17
    grid_raw: bytes = b""

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

    def room_grid(self) -> bytes:
        """One byte per cell: 0 unknown, 255 wall/obstacle, else room id."""
        size = self.width * self.height
        out = bytearray(size)
        for i, v in enumerate(self.grid_cells()[:size]):
            if v == 0:
                continue
            room = v >> 8
            out[i] = CELL_WALL if room == 0 else room & 0x3F
        return bytes(out)

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
                    "polygon": [cp(self.world_to_cell(p)) for p in fa.polygon],
                }
                for fa in self.forbiddens
            ],
            "walls": [
                {
                    "id": vw.id,
                    "start": cp(self.world_to_cell(vw.start)),
                    "end": cp(self.world_to_cell(vw.end)),
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
