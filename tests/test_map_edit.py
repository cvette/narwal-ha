"""No-go zone edits (/map/operation)."""

from __future__ import annotations

import pytest

from protocol.enums import ForbiddenType, ServiceResult
from protocol.map import decode_get_map_response
from protocol.map_edit import MapEditError, NoGoZone, build_no_go_request, decode_map_edit_result
from protocol.pb import Writer, parse


def _ops(req: bytes) -> list[dict]:
    """The forbidden-area operations of a request as plain dicts."""
    out = []
    for f in parse(req):
        if f.num != 4:
            continue
        [payload] = parse(f.value)
        assert payload.num == 4, "forbiddenAreaOperation"
        op = {g.num: g for g in parse(payload.value)}
        area = parse(op[2].value)
        points = [
            tuple(round(h.float, 3) for h in parse(p.value)) for p in area if p.num == 1
        ]
        out.append({"op": op[1].int, "points": points, **{g.num: g.int for g in area if g.num != 1}})
    return out


def test_add_and_delete(fixture_bin) -> None:
    mi = decode_get_map_response(fixture_bin("get_map"))  # one no-entry zone, id 1
    # Map: origin (-3, -2.5) m, 50 mm cells, border (-40, -30): world (0.5, 1.0) m
    # is display cell (70, 70), border-frame cell (30, 40).
    req = build_no_go_request(mi, add=[NoGoZone(1.0, 2.0, 0.5, 1.0, ForbiddenType.MOP)], delete=[1])
    header = {f.num: f.int for f in parse(req) if f.num < 4}
    assert header == {1: mi.map_id, 2: mi.map_version, 3: mi.edit_version}
    added, deleted = _ops(req)
    assert added == {"op": 1, "points": [(30.0, 40.0), (40.0, 40.0), (40.0, 60.0), (30.0, 60.0)], 2: 2, 3: 2}
    assert deleted["op"] == 2 and deleted[3] == 1 and deleted[2] == 3
    assert deleted["points"] == [(45.0, 5.0), (55.0, 5.0), (55.0, 15.0), (45.0, 15.0)], "sent back as read"


def test_bad_edits(fixture_bin) -> None:
    mi = decode_get_map_response(fixture_bin("get_map"))
    with pytest.raises(ValueError):
        build_no_go_request(mi)
    with pytest.raises(ValueError):
        build_no_go_request(mi, delete=[7])
    with pytest.raises(ValueError):
        build_no_go_request(mi, add=[NoGoZone(1, 1, 1, 2)])


def test_edit_result() -> None:
    ok = bytes(Writer().varint(1, 1).varint(3, 1077))
    assert decode_map_edit_result(ok) == (ServiceResult.PERFORM_SUCCESS, MapEditError.NONE)
    stale = bytes(Writer().varint(1, 2).varint(4, 1))
    assert decode_map_edit_result(stale) == (ServiceResult.PERFORM_GENERAL_FAILED, MapEditError.UNMATCHED_EDIT_VERSION)
