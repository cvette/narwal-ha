"""Map decoding against a /map/get_map payload and the Go golden output.

The payload is synthetic (scripts/make_synthetic_map.py): real structure, made-up
floor plan. The golden JSON is the Go client's decoding of the same bytes.
"""

from __future__ import annotations

import math

import pytest

from protocol.enums import ForbiddenType, ServiceResult
from protocol.map import (
    CELL_UNKNOWN,
    CELL_WALL,
    CellInt,
    MapInfo,
    decode_get_map_response,
    decode_static_map_payload,
)
from protocol.pb import Writer


@pytest.fixture
def live_map(fixture_bin) -> MapInfo:
    return decode_get_map_response(fixture_bin("get_map"))


def test_scalars_match_go(live_map: MapInfo, golden) -> None:
    gold = golden("get_map")
    assert live_map.result is ServiceResult.PERFORM_SUCCESS
    assert live_map.robot_has_map is gold["robotHasMap"]
    for attr, key in [
        ("map_id", "mapId"),
        ("map_version", "mapVersion"),
        ("edit_version", "editVersion"),
        ("resolution_mm", "resolutionMM"),
        ("width", "width"),
        ("height", "height"),
        ("border_left", "borderLeft"),
        ("border_bottom", "borderBottom"),
    ]:
        assert getattr(live_map, attr) == gold[key], attr
    assert math.isclose(live_map.origin_x, gold["originX"], abs_tol=1e-6)
    assert math.isclose(live_map.origin_y, gold["originY"], abs_tol=1e-6)
    assert len(live_map.grid_raw) == gold["gridRawLen"]


def test_rooms_doors_carpets_match_go(live_map: MapInfo, golden) -> None:
    gold = golden("get_map")
    assert [(r.id, r.name, r.color) for r in live_map.rooms] == [
        (r["ID"], r["Name"], r["Color"]) for r in gold["rooms"]
    ]
    assert [[(p.x, p.y) for p in d] for d in live_map.doors] == [
        [(p["x"], p["y"]) for p in d] for d in gold["doors"]
    ]
    assert [(c.id, [(p.x, p.y) for p in c.points]) for c in live_map.carpets] == [
        (c["id"], [(p["x"], p["y"]) for p in c["polygon"]]) for c in gold["carpets"]
    ]
    assert [(c.id, [(p.x, p.y) for p in c.points]) for c in live_map.no_carpets] == [
        (c["id"], [(p["x"], p["y"]) for p in c["polygon"]]) for c in gold["noCarpets"]
    ]
    assert [(f.id, int(f.type), f.mode) for f in live_map.forbiddens] == [
        (f["ID"], f["Type"], f["Mode"]) for f in gold["forbiddens"]
    ]
    for ours, theirs in zip(live_map.forbiddens[0].polygon, gold["forbiddens"][0]["Polygon"], strict=True):
        assert math.isclose(ours.x, theirs["x"], abs_tol=1e-6)
        assert math.isclose(ours.y, theirs["y"], abs_tol=1e-6)
    assert live_map.room_name(3) == "Hallway"


def test_to_json_matches_go_exactly(live_map: MapInfo, golden) -> None:
    gold = golden("get_map")["json"]
    ours = live_map.to_json()
    assert ours.keys() == gold.keys()
    assert ours["cellsB64"] == gold["cellsB64"], "per-cell room grid differs from Go"
    for key in ("originX", "originY", "resolutionM"):
        assert math.isclose(ours[key], gold[key], abs_tol=1e-6), key
    for key in gold.keys() - {"originX", "originY", "resolutionM", "cellsB64"}:
        assert ours[key] == gold[key], key


def test_room_grid_contents(live_map: MapInfo) -> None:
    grid = live_map.room_grid()
    assert len(grid) == live_map.width * live_map.height
    values = set(grid)
    assert {CELL_UNKNOWN, CELL_WALL} <= values
    assert {1, 2, 3, 4} <= values  # all four rooms appear
    assert values <= {CELL_UNKNOWN, CELL_WALL, 1, 2, 3, 4}


def test_border_frame_conversion(live_map: MapInfo) -> None:
    # First door point (12, -85) in the border frame -> display cell.
    c = live_map.border_to_cell(CellInt(12, -85))
    assert (c.col, c.row) == (12 - live_map.border_left, -85 - live_map.border_bottom)


def _point(x: float, y: float) -> Writer:
    return Writer().float_(1, x).float_(2, y)


def test_forbidden_and_wall_roundtrip() -> None:
    """Port of the Go TestDecodeForbiddenAndWallRoundTrip: world points go in,
    world_to_cell must recover the original cells."""
    src = MapInfo(resolution_mm=50, width=180, height=212, origin_x=-5.0, origin_y=-4.0)
    poly_cells = [(10, 20), (30, 20), (30, 40), (10, 40)]
    wall_cells = [(100, 50), (100, 90)]

    body = Writer().varint(1, 1, force=True).varint(2, 2).varint(3, 50).varint(4, 180).varint(5, 212)
    body.message(7, _point(-5.0, -4.0))
    fa = Writer()
    for col, row in poly_cells:
        p = src.cell_to_world(col, row)
        fa.message(1, _point(p.x, p.y))
    fa.varint(2, int(ForbiddenType.MOP)).varint(3, 7)
    body.message(9, fa)
    s, e = (src.cell_to_world(*c) for c in wall_cells)
    body.message(50, Writer().varint(1, 4).message(2, _point(s.x, s.y)).message(3, _point(e.x, e.y)))

    mi = decode_static_map_payload(bytes(body))
    assert len(mi.forbiddens) == 1 and len(mi.virtual_walls) == 1
    got = mi.forbiddens[0]
    assert (got.id, got.type) == (7, ForbiddenType.MOP)
    for p, (col, row) in zip(got.polygon, poly_cells, strict=True):
        c = mi.world_to_cell(p)
        assert math.isclose(c.col, col, abs_tol=1e-3) and math.isclose(c.row, row, abs_tol=1e-3)
    wall = mi.virtual_walls[0]
    assert wall.id == 4
    for p, (col, row) in zip((wall.start, wall.end), wall_cells, strict=True):
        c = mi.world_to_cell(p)
        assert math.isclose(c.col, col, abs_tol=1e-3) and math.isclose(c.row, row, abs_tol=1e-3)
    js = mi.to_json()
    assert js["forbiddens"][0]["type"] == 2 and len(js["walls"]) == 1


def test_empty_response() -> None:
    mi = decode_get_map_response(bytes(Writer().varint(1, 1)))
    assert mi.result is ServiceResult.PERFORM_SUCCESS
    assert not mi.robot_has_map and mi.room_grid() == b""
