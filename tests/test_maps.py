"""Several maps: /map/get_all_reduced_maps and /map/switch_map."""

from __future__ import annotations

from protocol.maps import MapSummary, build_switch_map_request, decode_all_maps
from protocol.pb import Writer, parse


def _map(map_id: int, name: str = "", main: bool = False, temp: bool = False, rooms=()) -> Writer:
    m = Writer().varint(1, map_id).varint(2, 382).string(28, name).boolean(30, main).boolean(37, temp)
    for i, room in enumerate(rooms, start=1):
        m.message(12, Writer().varint(1, i).string(3, room))
    return m


def test_all_maps() -> None:
    """Shaped like the real answer (one unnamed main map with four rooms) plus a second floor."""
    payload = (
        Writer().varint(1, 1)
        .message(2, _map(1, main=True, rooms=["Living room", "Bedroom", "Hall", "Bath"]))
        .message(2, _map(2, "Upstairs", rooms=["Office"]))
    )  # fmt: skip
    assert decode_all_maps(bytes(payload)) == [
        MapSummary(1, "", True, False, ("Living room", "Bedroom", "Hall", "Bath")),
        MapSummary(2, "Upstairs", False, False, ("Office",)),
    ]
    assert decode_all_maps(bytes(Writer().varint(1, 1))) == []


def test_switch_map_request() -> None:
    assert [(f.num, f.int) for f in parse(build_switch_map_request(2))] == [(1, 2)]
