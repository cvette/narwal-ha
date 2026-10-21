"""Start / end / locate requests (verified on a robot, see protocol/cleaning.py)."""

from __future__ import annotations

from protocol.cleaning import (
    CleanMode,
    TaskKind,
    build_clean_task_request,
    build_start_request,
)
from protocol.enums import FanLevel, MopHumidity
from protocol.pb import parse


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
