"""Render a MapInfo to PNG using only the standard library.

Rooms are coloured by id; walls, doors, carpets, no-carpet areas, forbidden
zones, virtual walls, furniture, camera detections and the dock are drawn on
top. The image is flipped so north is up as in the app. add_room_labels writes
room names on top when Pillow is installed; everything else uses only the
standard library.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math
import struct
import zlib

from .enums import ForbiddenType, ObstacleLabel
from .map import CELL_UNKNOWN, CELL_WALL, CellPoint, MapInfo

RGB = tuple[int, int, int]

# Index 0 is unused (room ids start at 1); colours match the Go client and web UI.
ROOM_PALETTE: tuple[RGB, ...] = (
    (24, 24, 28),
    (66, 135, 245),
    (245, 181, 66),
    (96, 201, 110),
    (224, 102, 178),
    (150, 120, 230),
    (230, 120, 120),
    (120, 200, 220),
    (200, 200, 120),
)


def room_color(room_id: int) -> RGB:
    if 0 < room_id < len(ROOM_PALETTE):
        return ROOM_PALETTE[room_id]
    return ROOM_PALETTE[((room_id - 1) % (len(ROOM_PALETTE) - 1)) + 1]


@dataclass(slots=True, frozen=True)
class Theme:
    background: RGB = (24, 24, 28)
    wall: RGB = (10, 10, 12)
    door: RGB = (255, 255, 255)
    carpet: RGB = (139, 94, 52)
    no_carpet: RGB = (255, 140, 0)
    no_go: RGB = (220, 38, 38)
    no_mop: RGB = (37, 99, 235)
    no_sweep: RGB = (234, 179, 8)
    virtual_wall: RGB = (220, 38, 38)
    furniture: RGB = (236, 236, 240)
    obstacle: RGB = (217, 70, 239)
    obstacle_alert: RGB = (239, 68, 68)  # pet waste, liquids
    dirt: RGB = (146, 94, 48)
    station: RGB = (250, 204, 21)
    outline: RGB = (0, 0, 0)


# Camera detections drawn in the alert colour.
ALERT_OBSTACLES = frozenset({ObstacleLabel.POOP, ObstacleLabel.LIQUID})


class _Canvas:
    __slots__ = ("height", "pixels", "width")

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 3)

    def set(self, x: int, y: int, c: RGB) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 3
            self.pixels[i : i + 3] = bytes(c)

    def blend(self, x: int, y: int, c: RGB, alpha: float) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 3
            for k in range(3):
                self.pixels[i + k] = round(self.pixels[i + k] * (1 - alpha) + c[k] * alpha)

    def line(self, x0: int, y0: int, x1: int, y1: int, c: RGB, thickness: int = 1) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        half = thickness // 2
        while True:
            for ox in range(-half, thickness - half):
                for oy in range(-half, thickness - half):
                    self.set(x0 + ox, y0 + oy, c)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def polyline(self, pts: Sequence[tuple[int, int]], c: RGB, closed: bool, thickness: int = 1) -> None:
        if len(pts) < 2:
            return
        pairs = zip(pts, pts[1:] + (pts[:1] if closed else []), strict=False)
        for (x0, y0), (x1, y1) in pairs:
            self.line(x0, y0, x1, y1, c, thickness)

    def fill_circle(self, cx: float, cy: float, radius: float, c: RGB) -> None:
        r2 = radius * radius
        for y in range(int(cy - radius), int(cy + radius) + 1):
            for x in range(int(cx - radius), int(cx + radius) + 1):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r2:
                    self.set(x, y, c)

    def fill_polygon(self, pts: Sequence[tuple[float, float]], c: RGB, alpha: float) -> None:
        """Even-odd fill sampled at pixel centres."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        n = len(pts)
        for y in range(max(0, int(min(ys))), min(self.height, int(max(ys)) + 1)):
            cy = y + 0.5
            xs: list[float] = []
            for i in range(n):
                (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % n]
                if (ya <= cy < yb) or (yb <= cy < ya):
                    xs.append(xa + (cy - ya) * (xb - xa) / (yb - ya))
            xs.sort()
            for xa, xb in zip(xs[::2], xs[1::2], strict=False):
                for x in range(max(0, round(xa)), min(self.width, round(xb))):
                    self.blend(x, y, c, alpha)

    def png(self) -> bytes:
        stride = self.width * 3
        raw = b"".join(
            b"\x00" + bytes(self.pixels[y * stride : (y + 1) * stride]) for y in range(self.height)
        )

        def chunk(kind: bytes, data: bytes) -> bytes:
            body = kind + data
            return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b"")
        )


@dataclass(slots=True, frozen=True)
class Viewport:
    """Which stored cells the image shows and how big a cell is.

    Pixel (x, y) of the image covers stored cell (col0 + x/scale,
    row1 - y/scale): the image is flipped so row 0 ends up at the bottom.
    """

    col0: int
    row0: int
    col1: int  # exclusive
    row1: int  # exclusive
    scale: int

    @property
    def size(self) -> tuple[int, int]:
        return ((self.col1 - self.col0) * self.scale, (self.row1 - self.row0) * self.scale)

    def corner(self, col: float, row: float) -> tuple[float, float]:
        """Image coords of a cell corner (world-derived points)."""
        return ((col - self.col0) * self.scale, (self.row1 - row) * self.scale)

    def center(self, col: float, row: float) -> tuple[int, int]:
        """Image coords of a cell centre (integer border-frame points)."""
        return (
            int((col - self.col0 + 0.5) * self.scale),
            int((self.row1 - row - 0.5) * self.scale),
        )


def content_viewport(mi: MapInfo, scale: int, padding: int = 2) -> Viewport:
    """Crop to the known area of the map, with a little padding."""
    w, h = mi.width, mi.height
    grid = mi.room_grid()
    cols = [i % w for i, v in enumerate(grid) if v != CELL_UNKNOWN]
    rows = [i // w for i, v in enumerate(grid) if v != CELL_UNKNOWN]
    if not cols:
        return Viewport(0, 0, w, h, scale)
    return Viewport(
        max(0, min(cols) - padding),
        max(0, min(rows) - padding),
        min(w, max(cols) + 1 + padding),
        min(h, max(rows) + 1 + padding),
        scale,
    )


def render_png(
    mi: MapInfo,
    scale: int = 4,
    *,
    crop: bool = True,
    theme: Theme | None = None,
) -> tuple[bytes, Viewport]:
    """Render the map. Returns the PNG bytes and the viewport used, so callers
    can place markers (robot, dock) in the same pixel frame."""
    theme = theme or Theme()
    scale = max(1, scale)
    vp = content_viewport(mi, scale) if crop else Viewport(0, 0, mi.width, mi.height, scale)
    width, height = vp.size
    canvas = _Canvas(width, height)

    # Rooms and walls, one stored row at a time, repeated `scale` times.
    grid = mi.room_grid()
    w = mi.width
    for out_row, row in enumerate(range(vp.row1 - 1, vp.row0 - 1, -1)):
        line = bytearray()
        for col in range(vp.col0, vp.col1):
            v = grid[row * w + col]
            if v == CELL_UNKNOWN:
                c = theme.background
            elif v == CELL_WALL:
                c = theme.wall
            else:
                c = room_color(v)
            line += bytes(c) * scale
        stride = width * 3
        for k in range(scale):
            start = (out_row * scale + k) * stride
            canvas.pixels[start : start + stride] = line

    thick = max(1, scale // 2)

    def centres(points: Iterable[CellPoint]) -> list[tuple[int, int]]:
        return [vp.center(p.col, p.row) for p in points]

    for poly in mi.carpets:
        pts = [mi.border_to_cell(p) for p in poly.points]
        canvas.fill_polygon([vp.corner(p.col + 0.5, p.row + 0.5) for p in pts], theme.carpet, 0.35)
        canvas.polyline(centres(pts), theme.carpet, closed=True)
    for poly in mi.no_carpets:
        canvas.polyline(centres(mi.border_to_cell(p) for p in poly.points), theme.no_carpet, closed=True, thickness=thick)
    for door in mi.doors:
        canvas.polyline(centres(mi.border_to_cell(p) for p in door), theme.door, closed=False, thickness=thick)

    fill = {
        ForbiddenType.SWEEP_MOP: theme.no_go,
        ForbiddenType.MOP: theme.no_mop,
        ForbiddenType.SWEEP: theme.no_sweep,
    }
    for fa in mi.forbiddens:
        c = fill.get(fa.type, theme.no_go)
        corners = [vp.corner(*_cp(mi.world_to_cell(p))) for p in fa.polygon]
        canvas.fill_polygon(corners, c, 0.35)
        canvas.polyline([(round(x), round(y)) for x, y in corners], c, closed=True, thickness=thick)
    for vw in mi.virtual_walls:
        (x0, y0), (x1, y1) = (vp.corner(*_cp(mi.world_to_cell(p))) for p in (vw.start, vw.end))
        canvas.line(round(x0), round(y0), round(x1), round(y1), theme.virtual_wall, thick)

    _draw_objects(canvas, mi, vp, theme, thick)
    return canvas.png(), vp


def furniture_corners(mi: MapInfo, f) -> list[CellPoint]:
    """The four corners of a furniture box in display cells (centre + size,
    rotated by its angle)."""
    centre = mi.border_point_to_cell(f.x, f.y)
    a = math.radians(f.angle)
    cos_a, sin_a = math.cos(a), math.sin(a)
    out = []
    for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        ox, oy = dx * f.width / 2, dy * f.height / 2
        out.append(CellPoint(centre.col + ox * cos_a - oy * sin_a, centre.row + ox * sin_a + oy * cos_a))
    return out


def _draw_objects(canvas: _Canvas, mi: MapInfo, vp: Viewport, theme: Theme, thick: int) -> None:
    """Furniture, camera detections and the dock, on top of everything else."""
    for f in mi.furniture:
        corners = [vp.corner(p.col, p.row) for p in furniture_corners(mi, f)]
        canvas.fill_polygon(corners, theme.furniture, 0.30)
        canvas.polyline([(round(x), round(y)) for x, y in corners], theme.furniture, closed=True, thickness=thick)

    size = max(3.0, vp.scale * 1.5)
    for d in mi.dirt:
        c = mi.border_point_to_cell(d.x, d.y)
        x, y = vp.corner(c.col, c.row)
        canvas.fill_circle(x, y, size + 1, theme.outline)
        canvas.fill_circle(x, y, size, theme.dirt)
    for o in mi.obstacles:
        c = mi.border_point_to_cell(o.x, o.y)
        x, y = vp.corner(c.col, c.row)
        colour = theme.obstacle_alert if o.label in ALERT_OBSTACLES else theme.obstacle
        outer = [(x, y - size - 1.5), (x + size + 1.5, y), (x, y + size + 1.5), (x - size - 1.5, y)]
        inner = [(x, y - size), (x + size, y), (x, y + size), (x - size, y)]
        canvas.fill_polygon(outer, theme.outline, 1.0)
        canvas.fill_polygon(inner, colour, 1.0)

    if mi.station is not None:
        c = mi.border_point_to_cell(mi.station.x, mi.station.y)
        x, y = vp.corner(c.col, c.row)
        radius = max(4.0, vp.scale * 2.5)
        canvas.fill_circle(x, y, radius + 1.5, theme.outline)
        canvas.fill_circle(x, y, radius, theme.station)
        # Heading: theta is counter-clockwise in map space; the image y axis is flipped.
        tip_x = x + math.cos(mi.station.theta) * radius * 1.8
        tip_y = y - math.sin(mi.station.theta) * radius * 1.8
        canvas.line(round(x), round(y), round(tip_x), round(tip_y), theme.outline, max(1, thick))


def _cp(c: CellPoint) -> tuple[float, float]:
    return (c.col, c.row)


def room_label_positions(mi: MapInfo) -> dict[int, tuple[int, int]]:
    """A stored cell (col, row) per room to put its label on: the room cell
    nearest the room's centroid, so L-shaped rooms still get a point inside."""
    w = mi.width
    cells: dict[int, list[tuple[int, int]]] = {}
    for idx, v in enumerate(mi.room_grid()):
        if v not in (CELL_UNKNOWN, CELL_WALL):
            cells.setdefault(v, []).append((idx % w, idx // w))
    out: dict[int, tuple[int, int]] = {}
    for rid, pts in cells.items():
        cx = sum(c for c, _ in pts) / len(pts)
        cy = sum(r for _, r in pts) / len(pts)
        out[rid] = min(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    return out


def add_room_labels(png: bytes, mi: MapInfo, vp: Viewport) -> bytes:
    """Write room names onto a rendered map. Needs Pillow (Home Assistant ships
    it); returns the image unchanged when Pillow is not installed."""
    try:
        from io import BytesIO  # noqa: PLC0415

        from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415
    except ImportError:
        return png
    image = Image.open(BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=max(12, vp.scale * 4))
    except TypeError:  # Pillow < 10.1 has no sized default font
        font = ImageFont.load_default()
    positions = room_label_positions(mi)
    for room in mi.rooms:
        if not room.name or room.id not in positions:
            continue
        x, y = vp.center(*positions[room.id])
        draw.text(
            (x, y), room.name, font=font, fill=(255, 255, 255),
            anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0),
        )  # fmt: skip
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
