"""Several maps (floors): listing them and switching the current one.

    GetAllReducedMaps_Response { 1 result, 2 maps[]: StaticMapPayload (reduced) }
    StaticMapPayload           { 1 mapId, 2 mapVersion, 12 roomInfos[],
                                 28 customName, 30 isMainMap, 37 isTempMap, … }
    SwitchMap_Request          { 1 mapId }

From app_protol (Narwal app 2.9.90). The reduced maps carry the same header
fields as a full map; only the names and flags are read here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .pb import WIRE_LEN, WIRE_VARINT, Writer, parse

URL_ALL_MAPS = "/map/get_all_reduced_maps"
URL_SWITCH_MAP = "/map/switch_map"


@dataclass(frozen=True, slots=True)
class MapSummary:
    id: int
    name: str = ""  # as named in the app; empty when never named
    main: bool = False
    temporary: bool = False
    rooms: tuple[str, ...] = ()


def _room_name(buf: bytes) -> str:
    for f in parse(buf):
        if f.num == 3 and f.wtype == WIRE_LEN:
            return f.value.decode("utf-8", "replace")
    return ""


def decode_all_maps(payload: bytes) -> list[MapSummary]:
    maps = []
    for f in parse(payload):
        if f.num != 2 or f.wtype != WIRE_LEN:
            continue
        values: dict[int, int] = {}
        name = ""
        rooms: list[str] = []
        for g in parse(f.value):
            if g.wtype == WIRE_VARINT:
                values[g.num] = g.int
            elif g.num == 28 and g.wtype == WIRE_LEN:
                name = g.value.decode("utf-8", "replace")
            elif g.num == 12 and g.wtype == WIRE_LEN:
                rooms.append(_room_name(g.value))
        maps.append(
            MapSummary(
                id=values.get(1, 0),
                name=name,
                main=bool(values.get(30)),
                temporary=bool(values.get(37)),
                rooms=tuple(r for r in rooms if r),
            )
        )
    return maps


def build_switch_map_request(map_id: int) -> bytes:
    return bytes(Writer().varint(1, map_id, force=True))
