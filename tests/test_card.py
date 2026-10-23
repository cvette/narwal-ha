"""Data for the map card (protocol/card.py)."""

from __future__ import annotations

import base64

from protocol.card import build_map_payload, map_version
from protocol.map import Point, decode_get_map_response


def test_map_payload(fixture_bin) -> None:
    mi = decode_get_map_response(fixture_bin("get_map"))
    payload = build_map_payload(mi)
    assert payload["image"].startswith("data:image/png;base64,")
    assert payload["version"] == map_version(mi)
    grid = payload["grid"]
    cells = base64.b64decode(grid["data"])
    assert len(cells) == grid["width"] * grid["height"]
    assert (payload["width"], payload["height"]) == (grid["width"] * 4, grid["height"] * 4)
    assert {r["id"] for r in payload["rooms"]} == set(cells) - {0}

    # A point in the living room lands on a living-room cell of the grid.
    t = payload["transform"]
    x, y = -0.75, -1.5
    px = ((x - t["origin_x"]) / t["resolution"] - t["col0"]) * t["scale"]
    py = (t["row1"] - (y - t["origin_y"]) / t["resolution"]) * t["scale"]
    assert cells[int(py // 4) * grid["width"] + int(px // 4)] == 1
    cell = mi.world_to_cell(Point(x, y))
    assert mi.room_grid()[int(cell.row) * mi.width + int(cell.col)] == 1
