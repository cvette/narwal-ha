"""Map decoding against a /map/get_map payload and the Go golden output.

The payload is synthetic (scripts/make_synthetic_map.py): real structure, made-up
floor plan. The golden JSON is the Go client's decoding of the same bytes.
"""

from __future__ import annotations

from dataclasses import replace
import math
import time

import pytest

from protocol.enums import (
    DirtLabel,
    DirtStatus,
    ForbiddenType,
    FurnitureType,
    ObstacleLabel,
    ServiceResult,
)
from protocol.map import (
    CELL_UNKNOWN,
    CELL_WALL,
    FLAG_BLOCKED,
    FLAG_CARPET,
    FLAG_FREE,
    CellInt,
    CellPoint,
    MapInfo,
    decode_display_map,
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


def test_dock_and_robot_pose(live_map: MapInfo) -> None:
    dock = live_map.station
    assert dock is not None and live_map.robot_pose == dock
    c = live_map.border_point_to_cell(dock.x, dock.y)
    assert (c.col, c.row) == (35.0, 48.5)
    assert math.isclose(dock.theta, -1.5708, abs_tol=1e-4)
    assert live_map.room_name(live_map.room_at(dock.x, dock.y)) == "Living room"


def test_furniture(live_map: MapInfo) -> None:
    got = [
        (f.id, f.type, live_map.border_point_to_cell(f.x, f.y), f.width, f.height, f.angle)
        for f in live_map.furniture
    ]
    assert got == [
        (1, FurnitureType.SOFA_MULTI, CellPoint(30.0, 30.0), 20.0, 8.0, 0.0),
        (2, FurnitureType.DOUBLE_BED, CellPoint(40.0, 80.0), 30.0, 16.0, 180.0),
    ]
    rooms = [live_map.room_name(live_map.room_at(f.x, f.y)) for f in live_map.furniture]
    assert rooms == ["Living room", "Bedroom"]


def test_camera_detections(live_map: MapInfo) -> None:
    assert [(o.id, o.label, live_map.room_name(live_map.room_at(o.x, o.y))) for o in live_map.obstacles] == [
        (1, ObstacleLabel.CABLE, "Living room"),
        (2, ObstacleLabel.SOCKS, "Hallway"),
        (3, ObstacleLabel.POOP, "Kitchen"),
    ]
    assert all(o.task_id == 1791364633432638116 for o in live_map.obstacles)
    (dirt,) = live_map.dirt
    assert (dirt.label, dirt.status) == (DirtLabel.LIQUID_MANY, DirtStatus.CLEANED)
    assert live_map.room_name(live_map.room_at(dirt.x, dirt.y)) == "Kitchen"


def test_cell_flags(live_map: MapInfo) -> None:
    flags = live_map.flag_grid()
    rooms = live_map.room_grid()
    w = live_map.width
    assert len(flags) == len(rooms)
    assert flags[50 * w + 110] == 0, "unknown cells (outside the house) have no flags"
    assert flags[9 * w + 30] == 0x28, "walls"
    assert flags[40 * w + 30] == FLAG_FREE, "plain floor"
    assert flags[25 * w + 25] == FLAG_FREE | FLAG_CARPET, "carpet"
    assert flags[80 * w + 66] == FLAG_BLOCKED, "wardrobe strip"
    assert rooms[80 * w + 66] == 4, "blocked cells keep their room"
    blocked = sum(1 for f in flags if f & FLAG_BLOCKED)
    assert blocked == 6 * 20


def test_room_grid_is_cached(live_map: MapInfo) -> None:
    first = live_map.room_grid()
    assert live_map.room_grid() is first, "second call must not decode again"

    copy = replace(live_map)
    assert copy.room_grid() == first  # fresh cache, same content

    live_map.grid_raw = b""
    assert live_map.room_grid() == bytes(live_map.width * live_map.height), "new grid bytes, new result"


def test_room_lookups_are_fast(live_map: MapInfo) -> None:
    """Attributes look up the room of every object on each state write; this
    once took half a second in Home Assistant because each lookup decoded the
    whole grid."""
    start = time.perf_counter()
    for _ in range(200):
        for o in live_map.obstacles:
            live_map.room_at(o.x, o.y)
    assert time.perf_counter() - start < 0.5


def test_room_at_outside_map(live_map: MapInfo) -> None:
    assert live_map.room_at(-1000.0, -1000.0) is None


def test_display_map() -> None:
    def pose(x: float, y: float, theta: float) -> Writer:
        return Writer().message(1, Writer().float_(1, x).float_(2, y)).float_(2, theta)

    body = bytes(
        Writer().message(1, pose(3.25, -27.75, -1.25)).message(2, Writer().varint(1, 1))
        .varint(3, 172).message(5, pose(-2.0, 9.5, -1.5)).varint(10, 1792598775412)
    )  # fmt: skip
    dm = decode_display_map(body)
    assert (dm.robot.x, dm.robot.y, dm.robot.theta) == (3.25, -27.75, -1.25)
    assert (dm.dock.x, dm.dock.y) == (-2.0, 9.5)
    assert dm.timestamp_ms == 1792598775412
    assert decode_display_map(b"").robot is None


def test_empty_response() -> None:
    mi = decode_get_map_response(bytes(Writer().varint(1, 1)))
    assert mi.result is ServiceResult.PERFORM_SUCCESS
    assert not mi.robot_has_map and mi.room_grid() == b""
