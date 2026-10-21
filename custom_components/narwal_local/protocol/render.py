"""Render a MapInfo to PNG using only the standard library.

Rooms are coloured by id; walls, doors, carpets, no-carpet areas, forbidden
zones, virtual walls, furniture, camera detections and the dock are drawn on
top. The image is flipped so north is up as in the app. add_room_labels writes
room names on top when Pillow is installed; everything else uses only the
standard library.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
import math
import struct
from typing import Any
import zlib

from .enums import ForbiddenType, ObstacleLabel
from .icons import DOCK_ICON, FONT_PATH, dirt_icon, furniture_icon, glyph, obstacle_icon
from .map import CELL_UNKNOWN, CELL_WALL, FLAG_BLOCKED, CellPoint, MapInfo, Pose

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


def blocked_color(room_id: int, theme: Theme) -> RGB:
    """The room colour, darkened, for cells the robot cannot enter."""
    return tuple(round(c * theme.blocked_shade) for c in room_color(room_id))


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
    furniture_icon: RGB = (40, 40, 48)
    blocked_shade: float = 0.6  # brightness of blocked cells relative to the room
    robot: RGB = (16, 185, 129)
    path: RGB = (255, 255, 255)
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
    # Room cells the robot cannot enter (FLAG_BLOCKED) get a darker shade.
    grid = mi.room_grid()
    flags = mi.flag_grid()
    w = mi.width
    for out_row, row in enumerate(range(vp.row1 - 1, vp.row0 - 1, -1)):
        line = bytearray()
        for col in range(vp.col0, vp.col1):
            v = grid[row * w + col]
            if v == CELL_UNKNOWN:
                c = theme.background
            elif v == CELL_WALL:
                c = theme.wall
            elif flags[row * w + col] & FLAG_BLOCKED:
                c = blocked_color(v, theme)
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


def _inside_furniture(mi: MapInfo, col: float, row: float, margin: float) -> bool:
    """Whether a display cell lies within a furniture box grown by `margin` cells."""
    for f in mi.furniture:
        centre = mi.border_point_to_cell(f.x, f.y)
        a = math.radians(f.angle)
        dx, dy = col - centre.col, row - centre.row
        # Rotate into the box's own axes.
        lx = dx * math.cos(a) + dy * math.sin(a)
        ly = -dx * math.sin(a) + dy * math.cos(a)
        if abs(lx) <= f.width / 2 + margin and abs(ly) <= f.height / 2 + margin:
            return True
    return False


def room_label_positions(mi: MapInfo, avoid_margin: float = 3.0) -> dict[int, tuple[int, int]]:
    """A stored cell (col, row) per room to put its label on: the room cell
    nearest the room's centroid that is clear of furniture (whose own labels
    sit there), so L-shaped rooms still get a point inside."""
    w = mi.width
    cells: dict[int, list[tuple[int, int]]] = {}
    for idx, v in enumerate(mi.room_grid()):
        if v not in (CELL_UNKNOWN, CELL_WALL):
            cells.setdefault(v, []).append((idx % w, idx // w))
    out: dict[int, tuple[int, int]] = {}
    for rid, pts in cells.items():
        cx = sum(c for c, _ in pts) / len(pts)
        cy = sum(r for _, r in pts) / len(pts)
        ranked = sorted(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        out[rid] = next(
            (p for p in ranked if not _inside_furniture(mi, p[0] + 0.5, p[1] + 0.5, avoid_margin)),
            ranked[0],
        )
    return out


NameFn = Callable[[Any], str]


def _overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """Whether two (left, top, right, bottom) boxes intersect."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _pil():
    """(Image, ImageDraw, ImageFont) or None when Pillow is not installed."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415
    except ImportError:
        return None
    return Image, ImageDraw, ImageFont


def _decode(png: bytes, pil):
    from io import BytesIO  # noqa: PLC0415

    return pil[0].open(BytesIO(png)).convert("RGBA")


def _encode(image) -> bytes:
    from io import BytesIO  # noqa: PLC0415

    out = BytesIO()
    image.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def add_labels(
    png: bytes,
    mi: MapInfo,
    vp: Viewport,
    *,
    obstacle_name: NameFn | None = None,
    furniture_name: NameFn | None = None,
    icons: bool = False,
    theme: Theme | None = None,
) -> bytes:
    """Write room names onto a rendered map, plus furniture and detected-object
    names when a naming function is given, and Material Design Icons for
    furniture, detections, dirt and the dock when `icons` is set. Needs Pillow
    (Home Assistant ships it); returns the image unchanged without it."""
    if (pil := _pil()) is None:
        return png
    image = _compose_labels(
        _decode(png, pil), mi, vp, pil,
        obstacle_name=obstacle_name, furniture_name=furniture_name,
        icons=icons, theme=theme or Theme(),
    )  # fmt: skip
    return _encode(image)


def _compose_labels(
    image,
    mi: MapInfo,
    vp: Viewport,
    pil,
    *,
    obstacle_name: NameFn | None,
    furniture_name: NameFn | None,
    icons: bool,
    theme: Theme,
):
    """Draw labels and icons onto an RGBA image (also a transparent one, to
    build a reusable overlay). Returns the resulting RGBA image."""
    _, image_draw, image_font = pil
    draw = image_draw.Draw(image)

    def font(size: float):
        try:
            return image_font.load_default(size=size)
        except TypeError:  # Pillow < 10.1 has no sized default font
            return image_font.load_default()

    def text(xy: tuple[float, float], label: str, size_font, anchor: str) -> None:
        draw.text(
            xy, label, font=size_font, fill=(255, 255, 255),
            anchor=anchor, stroke_width=2, stroke_fill=(0, 0, 0),
        )  # fmt: skip

    small = font(max(9, vp.scale * 2.5))
    if furniture_name is not None:
        for f in mi.furniture:
            c = mi.border_point_to_cell(f.x, f.y)
            text(vp.corner(c.col, c.row), furniture_name(f.type), small, "mm")
    if obstacle_name is not None:
        offset = max(3.0, vp.scale * 1.5) + 4
        dock_box = None
        if mi.station is not None:
            c = mi.border_point_to_cell(mi.station.x, mi.station.y)
            dx, dy = vp.corner(c.col, c.row)
            r = max(4.0, vp.scale * 2.5) * 1.8  # symbol plus heading line
            dock_box = (dx - r, dy - r, dx + r, dy + r)
        for o in mi.obstacles:
            c = mi.border_point_to_cell(o.x, o.y)
            x, y = vp.corner(c.col, c.row)
            label = obstacle_name(o.label)
            xy, anchor = (x + offset, y), "lm"
            if dock_box is not None and _overlaps(
                draw.textbbox(xy, label, font=small, anchor=anchor, stroke_width=2), dock_box
            ):
                xy, anchor = (x - offset, y), "rm"  # the other side of the marker
            text(xy, label, small, anchor)

    if icons:
        image = _draw_icons(image, pil, mi, vp, theme)
        draw = image_draw.Draw(image)

    large = font(max(12, vp.scale * 4))
    positions = room_label_positions(mi)
    for room in mi.rooms:
        if room.name and room.id in positions:
            text(vp.center(*positions[room.id]), room.name, large, "mm")
    return image


ICON_SUPERSAMPLE = 3  # icon layer is drawn this much larger, then scaled down smoothly


def _draw_icons(image, pil, mi: MapInfo, vp: Viewport, theme: Theme):
    """Icons on top of the stdlib markers (badges cover the diamonds and dots).

    Pillow does not anti-alias circles, so the icon layer is drawn at
    ICON_SUPERSAMPLE times the size and box-downsampled; the result is
    composited over the image (RGBA). Returns the new image.
    """
    if not FONT_PATH.exists():
        return image
    pil_image, pil_draw, image_font = pil
    s = ICON_SUPERSAMPLE
    layer = pil_image.new("RGBA", (image.width * s, image.height * s), (0, 0, 0, 0))
    draw = pil_draw.Draw(layer)

    def icon(x: float, y: float, name: str, size: float, colour: RGB) -> None:
        if (ch := glyph(name)) is not None:
            font = image_font.truetype(str(FONT_PATH), max(8, round(size * s)))
            draw.text((x * s, y * s), ch, font=font, fill=colour, anchor="mm")

    def disc(x: float, y: float, radius: float, colour: RGB, ring: float = 2.0) -> None:
        """A filled circle with an even outline ring (two concentric discs)."""
        outer, inner = radius * s, (radius - ring) * s
        draw.ellipse((x * s - outer, y * s - outer, x * s + outer, y * s + outer), fill=theme.outline)
        draw.ellipse((x * s - inner, y * s - inner, x * s + inner, y * s + inner), fill=colour)

    for f in mi.furniture:
        c = mi.border_point_to_cell(f.x, f.y)
        size = min(max(min(f.width, f.height) * vp.scale * 0.7, 14), 40)
        icon(*vp.corner(c.col, c.row), furniture_icon(f.type), size, theme.furniture_icon)

    radius = max(7.0, vp.scale * 2.75)
    for d in mi.dirt:
        c = mi.border_point_to_cell(d.x, d.y)
        x, y = vp.corner(c.col, c.row)
        disc(x, y, radius, theme.dirt)
        icon(x, y, dirt_icon(d.label), radius * 1.45, (255, 255, 255))
    for o in mi.obstacles:
        c = mi.border_point_to_cell(o.x, o.y)
        x, y = vp.corner(c.col, c.row)
        disc(x, y, radius, theme.obstacle_alert if o.label in ALERT_OBSTACLES else theme.obstacle)
        icon(x, y, obstacle_icon(o.label), radius * 1.45, (255, 255, 255))

    if mi.station is not None:
        c = mi.border_point_to_cell(mi.station.x, mi.station.y)
        x, y = vp.corner(c.col, c.row)
        # Slightly larger than the stdlib dock so its jagged edge is covered;
        # the heading line stays visible outside the circle.
        dock_radius = max(4.0, vp.scale * 2.5) + 2
        disc(x, y, dock_radius, theme.station)
        icon(x, y, DOCK_ICON, dock_radius * 1.3, theme.outline)

    # BOX averages each block exactly: smooth edges, no Lanczos ringing.
    small = layer.resize(image.size, pil_image.Resampling.BOX)
    return pil_image.alpha_composite(image.convert("RGBA"), small)


def add_room_labels(png: bytes, mi: MapInfo, vp: Viewport) -> bytes:
    """Room names only (see add_labels)."""
    return add_labels(png, mi, vp)


PATH_SUPERSAMPLE = 2  # enough to smooth the thin path line; the layer spans the map


def _draw_path(image, pil, mi: MapInfo, vp: Viewport, path, theme: Theme) -> None:
    """The cleaning path, in place on an RGBA image."""
    if len(path) < 2:
        return
    pil_image, pil_draw, _ = pil
    s = PATH_SUPERSAMPLE
    layer = pil_image.new("RGBA", (image.width * s, image.height * s), (0, 0, 0, 0))

    def px(x: float, y: float) -> tuple[float, float]:
        c = mi.border_point_to_cell(x, y)
        cx, cy = vp.corner(c.col, c.row)
        return cx * s, cy * s

    pil_draw.Draw(layer).line(
        [px(x, y) for x, y in path], fill=(*theme.path, 190), width=2 * s, joint="curve"
    )
    image.alpha_composite(layer.resize(image.size, pil_image.Resampling.BOX))


def _draw_robot(image, pil, mi: MapInfo, vp: Viewport, robot: Pose, theme: Theme) -> None:
    """The robot marker with its heading, in place on an RGBA image. Only a
    small patch around the robot is supersampled."""
    pil_image, pil_draw, _ = pil
    s = ICON_SUPERSAMPLE
    c = mi.border_point_to_cell(robot.x, robot.y)
    cx, cy = vp.corner(c.col, c.row)
    r, ring = max(5.0, vp.scale * 2.5), 2.0
    half = math.ceil(r + ring + 1)
    x0, y0 = round(cx) - half, round(cy) - half
    size = 2 * half
    patch = pil_image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    draw = pil_draw.Draw(patch)
    x, y = (cx - x0) * s, (cy - y0) * s
    rr, rg = r * s, ring * s
    draw.ellipse((x - rr - rg, y - rr - rg, x + rr + rg, y + rr + rg), fill=(*theme.outline, 255))
    draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(*theme.robot, 255))
    # Heading: theta is counter-clockwise in map space; image y is flipped.
    tip = (x + math.cos(robot.theta) * rr * 0.75, y - math.sin(robot.theta) * rr * 0.75)
    draw.line([(x, y), tip], fill=(255, 255, 255, 255), width=max(1, round(rr / 3)))
    small = patch.resize((size, size), pil_image.Resampling.BOX)
    # Clip to the image so a robot at the edge does not raise.
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(size, image.width - x0), min(size, image.height - y0)
    if sx1 > sx0 and sy1 > sy0:
        image.alpha_composite(small, dest=(x0 + sx0, y0 + sy0), source=(sx0, sy0, sx1, sy1))


def add_robot(
    png: bytes,
    mi: MapInfo,
    vp: Viewport,
    robot: Pose | None,
    path: Sequence[tuple[float, float]] = (),
    theme: Theme | None = None,
) -> bytes:
    """Draw the cleaning path and the robot (position and heading) on a
    rendered map. Positions are border-frame points as in DisplayMap. Needs
    Pillow; returns the image unchanged without it."""
    if robot is None and len(path) < 2:
        return png
    if (pil := _pil()) is None:
        return png
    theme = theme or Theme()
    image = _decode(png, pil)
    _draw_path(image, pil, mi, vp, path, theme)
    if robot is not None:
        _draw_robot(image, pil, mi, vp, robot, theme)
    return _encode(image)


class MapRenderer:
    """Renders a map once, then frames with the robot and its path cheaply.

    The base map and the label/icon layer are built at construction; a frame
    only draws the path (under the labels) and the robot (on top) and encodes
    once. Without Pillow, frames are the plain stdlib map.
    """

    def __init__(self, mi: MapInfo, scale: int = 4, theme: Theme | None = None) -> None:
        self.mi = mi
        self.theme = theme or Theme()
        png, self.viewport = render_png(mi, scale, theme=self.theme)
        self._pil = _pil()
        self._plain = png
        self._static: bytes | None = None
        if self._pil is None:
            return
        self._base = _decode(png, self._pil)
        overlay = self._pil[0].new("RGBA", self._base.size, (0, 0, 0, 0))
        self._labels = _compose_labels(
            overlay, mi, self.viewport, self._pil,
            obstacle_name=None, furniture_name=None, icons=True, theme=self.theme,
        )  # fmt: skip

    def frame(self, robot: Pose | None = None, path: Sequence[tuple[float, float]] = ()) -> bytes:
        if self._pil is None:
            return self._plain
        if robot is None and len(path) < 2:
            if self._static is None:
                image = self._base.copy()
                image.alpha_composite(self._labels)
                self._static = _encode(image)
            return self._static
        image = self._base.copy()
        _draw_path(image, self._pil, self.mi, self.viewport, path, self.theme)
        image.alpha_composite(self._labels)
        if robot is not None:
            _draw_robot(image, self._pil, self.mi, self.viewport, robot, self.theme)
        return _encode(image)
