"""Start / end / locate requests (verified on a robot, see protocol/cleaning.py),
zones and cleaning plans."""

from __future__ import annotations

import pytest

from protocol.cleaning import (
    CleanMode,
    CleanPlan,
    TaskKind,
    build_clean_task_request,
    build_start_plan_request,
    build_start_request,
    build_zone_clean_request,
    decode_clean_plans,
)
from protocol.enums import FanLevel, MopHumidity
from protocol.map import decode_get_map_response
from protocol.pb import Writer, parse


def tree(buf: bytes) -> list:
    """Nested [num, value | subtree] lists for easy comparison."""
    out = []
    for f in parse(buf):
        out.append([f.num, f.value if isinstance(f.value, int) else tree(f.value)])
    return out


def test_room_clean_matches_the_request_the_robot_accepted() -> None:
    """Byte for byte the living-room request that started the real robot."""
    req = build_clean_task_request(1, [1], mode=CleanMode.SWEEP_MOP, fan=FanLevel.NORMAL, humidity=MopHumidity.WET)
    assert req.hex() == "0a18080112120a04080110011208080410022003380118012805"
    assert tree(req) == [[1, [[1, 1], [2, [[1, [[1, 1], [2, 1]]], [2, [[1, 4], [2, 2], [4, 3], [7, 1]]], [3, 1]]], [5, 5]]]]


def test_rooms_keep_their_order() -> None:
    req = build_clean_task_request(1, [3, 2], mode=CleanMode.SWEEP)
    items = [item for num, item in tree(req)[0][1] if num == 2]
    assert [dict(item)[1] for item in items] == [[[1, 1], [2, 3]], [[1, 1], [2, 2]]]
    assert [dict(item)[3] for item in items] == [1, 2], "order field"


def test_pass_counts_per_mode() -> None:
    def param(mode: CleanMode) -> dict:
        req = build_clean_task_request(1, [1], mode=mode, count=2)
        item = dict(tree(req)[0][1])[2]
        return dict(dict(item)[2])

    assert param(CleanMode.SWEEP)[5] == 2 and 7 not in param(CleanMode.SWEEP)
    assert param(CleanMode.MOP)[6] == 2
    assert param(CleanMode.SWEEP_MOP)[7] == 2
    assert (param(CleanMode.SWEEP_THEN_MOP)[5], param(CleanMode.SWEEP_THEN_MOP)[6]) == (2, 2)


def test_whole_map_variants() -> None:
    custom = tree(build_clean_task_request(1, None))
    assert [1, [[1, 3]]] in dict(custom[0][1])[2], "whole-map zone item"
    general = tree(build_clean_task_request(1, None, task_kind=TaskKind.GENERAL_SWEEP_MOP))
    assert general == [[1, [[1, 1], [5, 4]]]], "no items"


def test_easy_clean_request_for_the_ax3() -> None:
    req = build_start_request(1, [1], mode=CleanMode.SWEEP_MOP, fan=FanLevel.SUPER, humidity=MopHumidity.WET)
    assert tree(req) == [[1, 4], [2, 1], [3, [[1, 1], [2, 1], [6, [[1, 4], [3, 3], [4, 1]]]]]]


def test_zone_request_layout() -> None:
    """One item per zone: ZoneOption{type ZONE, id, 4 corners twice}."""
    req = build_zone_clean_request(1, [(5, 9, 2, 3)], mode=CleanMode.SWEEP, fan=FanLevel.STRONG, count=2)
    [[_, task]] = tree(req)
    assert task[0] == [1, 1] and task[-1] == [5, int(TaskKind.GENERAL_SWEEP)], "general task, not CUSTOM"
    [[_, item]] = [f for f in task if f[0] == 2]
    zone, param, order = item
    corners = [[[1, 2], [2, 3]], [[1, 5], [2, 3]], [[1, 5], [2, 9]], [[1, 2], [2, 9]]]
    assert zone == [1, [[1, 2], [2, 1], *([3, c] for c in corners), *([4, c] for c in corners)]]
    assert param == [2, [[1, int(CleanMode.SWEEP)], [2, 3], [4, 2], [5, 2]]]
    assert order == [3, 1]


def test_zones_keep_their_order_and_negative_cells() -> None:
    req = build_zone_clean_request(1, [(-10, -20, -5, -15), (0, 0, 4, 4)])
    items = [f[1] for f in tree(req)[0][1] if f[0] == 2]
    assert [item[0][1][1] for item in items] == [[2, 1], [2, 2]], "zone ids follow the order"
    first_corner = items[0][0][1][2][1]
    assert [v for _, v in first_corner] == [(-10) & (2**64 - 1), (-20) & (2**64 - 1)], "int32 as 64-bit varint"


def test_zone_without_area_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_zone_clean_request(1, [(3, 3, 3, 8)])
    with pytest.raises(ValueError):
        build_zone_clean_request(1, [])
    with pytest.raises(ValueError):
        build_zone_clean_request(1, [(0, 0, 4, 4)], mode=CleanMode.SMART)


def test_world_rect_to_grid(fixture_bin) -> None:
    mi = decode_get_map_response(fixture_bin("get_map"))  # origin (-3, -2.5) m, 50 mm, border (-40, -30)
    assert mi.world_to_border(-2.0, -1.5) == (20 - 40, 20 - 30)
    assert mi.world_rect_to_grid(-2.0, -1.5, -1.0, -1.0) == (-20, -10, 0, 0)


def test_clean_plans() -> None:
    plan = Writer().varint(1, 7).varint(2, 1).varint(3, 4).varint(4, 1).string(5, "Küche").varint(8, 2)
    other = Writer().varint(1, 3).varint(2, 1).varint(3, 9).varint(8, 1)
    plans = decode_clean_plans(bytes(Writer().varint(1, 1).message(2, plan).message(2, other)))
    assert [p.id for p in plans] == [3, 7], "sorted by the app's order"
    assert plans[1] == CleanPlan(id=7, map_id=1, mode=CleanMode.SWEEP_MOP, custom=True, name="Küche", order=2)
    assert plans[0].mode == 9, "unknown modes stay numeric"
    assert decode_clean_plans(bytes(Writer().varint(1, 1))) == []
    assert tree(build_start_plan_request(7, 1)) == [[1, 7], [2, 1]]
