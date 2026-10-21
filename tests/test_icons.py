"""Icon mapping and the bundled Material Design Icons subset."""

from __future__ import annotations

from io import BytesIO

import pytest

from protocol.enums import DirtLabel, FurnitureType, ObstacleLabel
from protocol.icons import (
    DIRT_ICONS,
    DOCK_ICON,
    FONT_PATH,
    FURNITURE_ICONS,
    OBSTACLE_ICONS,
    all_icon_names,
    codepoints,
    furniture_icon,
    glyph,
    obstacle_icon,
)
from protocol.map import MapInfo, decode_get_map_response
from protocol.render import Theme, add_labels, render_png, room_color


def test_every_type_has_an_icon() -> None:
    assert set(OBSTACLE_ICONS) == set(ObstacleLabel)
    assert set(FURNITURE_ICONS) == set(FurnitureType)
    assert set(DIRT_ICONS) == set(DirtLabel)


def test_subset_holds_every_mapped_icon() -> None:
    assert FONT_PATH.exists()
    assert set(codepoints()) == all_icon_names()
    assert glyph(DOCK_ICON) is not None
    # MDI codepoints live in the supplementary private use area.
    assert all(0xF0000 <= cp <= 0xFFFFD for cp in codepoints().values())


def test_unknown_values_fall_back() -> None:
    assert obstacle_icon(999) == OBSTACLE_ICONS[ObstacleLabel.UNSPECIFIED]
    assert furniture_icon(999) == FURNITURE_ICONS[FurnitureType.UNSPECIFIED]
    assert glyph("no-such-icon") is None


@pytest.fixture
def live_map(fixture_bin) -> MapInfo:
    return decode_get_map_response(fixture_bin("get_map"))


def test_icons_are_drawn(live_map: MapInfo) -> None:
    pil = pytest.importorskip("PIL.Image")
    theme = Theme()
    png, vp = render_png(live_map, 4)
    plain = add_labels(png, live_map, vp)
    with_icons = add_labels(png, live_map, vp, icons=True, theme=theme)
    assert with_icons != plain

    img = pil.open(BytesIO(with_icons)).convert("RGB")
    cable = next(o for o in live_map.obstacles if o.label is ObstacleLabel.CABLE)
    c = live_map.border_point_to_cell(cable.x, cable.y)
    x, y = vp.corner(c.col, c.row)
    # A badge in the obstacle colour, with the white glyph inside it.
    ring = [img.getpixel((round(x) + dx, round(y))) for dx in range(-9, 10)]
    assert theme.obstacle in ring
    assert (255, 255, 255) in [img.getpixel((round(x) + dx, round(y) + dy)) for dx in range(-4, 5) for dy in range(-4, 5)]


def test_badge_edges_are_anti_aliased(live_map: MapInfo) -> None:
    """Along a badge's outer edge, pixels blend outline and floor colour
    instead of jumping between the two (supersampled icon layer)."""
    import math

    pil = pytest.importorskip("PIL.Image")
    theme = Theme()
    png, vp = render_png(live_map, 4)
    img = pil.open(BytesIO(add_labels(png, live_map, vp, icons=True, theme=theme))).convert("RGB")
    cable = next(o for o in live_map.obstacles if o.label is ObstacleLabel.CABLE)
    c = live_map.border_point_to_cell(cable.x, cable.y)
    x, y = vp.corner(c.col, c.row)
    radius = max(7.0, vp.scale * 2.75)
    floor = room_color(1)  # the cable lies in the living room
    edge = {
        img.getpixel((round(x + radius * math.cos(a)), round(y + radius * math.sin(a))))
        for a in (math.radians(d) for d in range(0, 360, 5))
    }
    blended = edge - {theme.outline, floor}
    assert len(blended) >= 3, f"edge has only hard colours: {edge}"
