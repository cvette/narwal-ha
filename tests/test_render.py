"""PNG renderer: valid file, right size, right colours."""

from __future__ import annotations

import struct
import zlib

import pytest

from protocol.enums import ForbiddenType
from protocol.map import ForbiddenArea, MapInfo, decode_get_map_response
from protocol.render import Theme, render_png, room_color


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
    png, vp = render_png(live_map, scale, crop=False)
    width, height, pixels = decode_png(png)
    assert (width, height) == (live_map.width * scale, live_map.height * scale) == vp.size

    grid = live_map.room_grid()
    # Every room-coloured cell renders its room colour unless an overlay sits on it:
    # check a sample of cells away from doors/carpets by requiring a full match rate.
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
    assert matched / checked > 0.85  # carpets and zones cover the rest


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
