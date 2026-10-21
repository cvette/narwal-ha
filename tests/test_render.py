"""PNG renderer: valid file, right size, right colours."""

from __future__ import annotations

from dataclasses import replace
import struct
import zlib

import pytest

from protocol.enums import ForbiddenType
from protocol.map import ForbiddenArea, MapInfo, decode_get_map_response
from protocol.enums import ObstacleLabel
from protocol.render import (
    Theme,
    _overlaps,
    add_labels,
    add_room_labels,
    furniture_corners,
    render_png,
    room_color,
    room_label_positions,
)


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Minimal reader for our own output: 8-bit RGB, filter 0 on every row."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, width, height = 8, b"", 0, 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(kind + body), kind
        if kind == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert (depth, ctype) == (8, 2)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 3 + 1
    assert len(raw) == stride * height
    assert all(raw[y * stride] == 0 for y in range(height))
    pixels = b"".join(raw[y * stride + 1 : (y + 1) * stride] for y in range(height))
    return width, height, pixels


def pixel(width: int, pixels: bytes, x: int, y: int) -> tuple[int, int, int]:
    i = (y * width + x) * 3
    return tuple(pixels[i : i + 3])


@pytest.fixture
def live_map(fixture_bin) -> MapInfo:
    return decode_get_map_response(fixture_bin("get_map"))


def test_uncropped_size_and_room_colours(live_map: MapInfo) -> None:
    scale = 2
    # Without overlays every room cell must show exactly its room colour.
    bare = replace(
        live_map, doors=[], carpets=[], no_carpets=[], forbiddens=[], virtual_walls=[],
        furniture=[], obstacles=[], dirt=[], station=None,
    )  # fmt: skip
    png, vp = render_png(bare, scale, crop=False)
    width, height, pixels = decode_png(png)
    assert (width, height) == (live_map.width * scale, live_map.height * scale) == vp.size

    grid = live_map.room_grid()
    checked = matched = 0
    for idx in range(0, len(grid), 37):
        rid = grid[idx]
        if rid in (0, 255):
            continue
        col, row = idx % live_map.width, idx // live_map.width
        x, y = col * scale, (live_map.height - 1 - row) * scale  # flipped
        checked += 1
        matched += pixel(width, pixels, x, y) == room_color(rid)
    assert checked > 50
    assert matched == checked


def test_crop_keeps_all_known_cells(live_map: MapInfo) -> None:
    png, vp = render_png(live_map, 1, crop=True)
    width, height, _ = decode_png(png)
    assert (width, height) == vp.size
    assert width < live_map.width or height < live_map.height
    grid = live_map.room_grid()
    for idx, v in enumerate(grid):
        if v:
            col, row = idx % live_map.width, idx // live_map.width
            assert vp.col0 <= col < vp.col1 and vp.row0 <= row < vp.row1


def test_label_positions_lie_inside_their_rooms(live_map: MapInfo) -> None:
    grid = live_map.room_grid()
    positions = room_label_positions(live_map)
    assert set(positions) == {r.id for r in live_map.rooms}
    for rid, (col, row) in positions.items():
        assert grid[row * live_map.width + col] == rid


def test_room_labels_change_pixels_not_size(live_map: MapInfo) -> None:
    pytest.importorskip("PIL")
    png, vp = render_png(live_map, 4)
    labelled = add_room_labels(png, live_map, vp)
    assert labelled != png
    width, height, _ = decode_png_any(labelled)
    assert (width, height) == vp.size


def test_room_labels_avoid_furniture(live_map: MapInfo) -> None:
    """The bedroom's centroid lies on the bed; its label must move off it."""
    grid = live_map.room_grid()
    for rid, (col, row) in room_label_positions(live_map).items():
        assert grid[row * live_map.width + col] == rid
        for f in live_map.furniture:
            corners = furniture_corners(live_map, f)
            cols = [p.col for p in corners]
            rows = [p.row for p in corners]
            inside = min(cols) <= col + 0.5 <= max(cols) and min(rows) <= row + 0.5 <= max(rows)
            assert not inside, f"room {rid} label sits on furniture {f.id}"


def test_box_overlap() -> None:
    assert _overlaps((0, 0, 10, 10), (5, 5, 15, 15))
    assert not _overlaps((0, 0, 10, 10), (10, 0, 20, 10)), "touching edges do not overlap"
    assert not _overlaps((0, 0, 10, 10), (0, 11, 10, 20))


def test_object_names_are_written(live_map: MapInfo) -> None:
    pytest.importorskip("PIL")
    png, vp = render_png(live_map, 4)
    rooms_only = add_room_labels(png, live_map, vp)
    named = add_labels(
        png, live_map, vp,
        obstacle_name=lambda label: label.name.title(),
        furniture_name=lambda ftype: ftype.name.title(),
    )  # fmt: skip
    assert named != rooms_only
    assert decode_png_any(named)[:2] == vp.size


def decode_png_any(data: bytes) -> tuple[int, int, bytes]:
    """Size via Pillow (its encoder may use filters our minimal reader skips)."""
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(data))
    return img.width, img.height, b""


def test_dock_and_detections_are_drawn(live_map: MapInfo) -> None:
    theme = Theme()
    png, vp = render_png(live_map, 4, crop=False, theme=theme)
    width, _, pixels = decode_png(png)

    def at(x: float, y: float) -> tuple[int, int, int]:
        c = live_map.border_point_to_cell(x, y)
        px, py = vp.corner(c.col, c.row)
        return pixel(width, pixels, int(px), int(py))

    dock = live_map.station
    # The heading line starts at the centre; sample beside it.
    c = live_map.border_point_to_cell(dock.x, dock.y)
    px, py = vp.corner(c.col, c.row)
    assert pixel(width, pixels, int(px) - 4, int(py) - 2) == theme.station
    poop = next(o for o in live_map.obstacles if o.label is ObstacleLabel.POOP)
    cable = next(o for o in live_map.obstacles if o.label is ObstacleLabel.CABLE)
    assert at(poop.x, poop.y) == theme.obstacle_alert
    assert at(cable.x, cable.y) == theme.obstacle
    assert at(live_map.dirt[0].x, live_map.dirt[0].y) == theme.dirt


def test_furniture_corners_follow_angle(live_map: MapInfo) -> None:
    sofa, bed = live_map.furniture
    corners = furniture_corners(live_map, sofa)
    cols = sorted(round(p.col, 6) for p in corners)
    rows = sorted(round(p.row, 6) for p in corners)
    assert (cols[0], cols[-1], rows[0], rows[-1]) == (20.0, 40.0, 26.0, 34.0)
    # 180° turns the box onto itself.
    bed_cols = sorted(round(p.col, 6) for p in furniture_corners(live_map, bed))
    assert (bed_cols[0], bed_cols[-1]) == (25.0, 55.0)
    turned = replace(sofa, angle=90.0)
    cols = sorted(round(p.col, 6) for p in furniture_corners(live_map, turned))
    assert (cols[0], cols[-1]) == (26.0, 34.0), "90° swaps width and height"


def test_forbidden_zone_is_drawn() -> None:
    mi = MapInfo(resolution_mm=50, width=20, height=20, origin_x=0.0, origin_y=0.0)
    mi.grid_raw = b""  # all unknown
    mi.forbiddens.append(
        ForbiddenArea(
            id=1,
            type=ForbiddenType.SWEEP_MOP,
            polygon=[mi.cell_to_world(*c) for c in [(5, 5), (15, 5), (15, 15), (5, 15)]],
        )
    )
    theme = Theme()
    png, _ = render_png(mi, 4, crop=False, theme=theme)
    width, _, pixels = decode_png(png)
    inside = pixel(width, pixels, 10 * 4, (20 - 10) * 4)
    assert inside != theme.background
    assert inside[0] > inside[2], "no-go fill should be red-tinted"
