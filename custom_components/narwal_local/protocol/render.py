"""Render a MapInfo to PNG using only the standard library.

Rooms are coloured by id; walls, doors, carpets, no-carpet areas, forbidden
zones and virtual walls are drawn on top. The image is flipped so north is up
as in the app. Room labels need a font and are left to the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import struct
import zlib

from .enums import ForbiddenType
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

    return canvas.png(), vp


def _cp(c: CellPoint) -> tuple[float, float]:
    return (c.col, c.row)
