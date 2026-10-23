"""Map edits: adding and deleting no-go zones.

The app edits the map with /map/operation:

    MapOperation_Request  { 1 mapId, 2 mapVersion, 3 editVersion,
                            4 operations[]: MapOperationPayload }
    MapOperationPayload   { 4 forbiddenAreaOperation, … (rooms, carpets, …) }
    ForbiddenAreaOperation{ 1 operation (1 SET, 2 DELETE), 2 forbidden }
    ForbiddenArea         { 1 polygon[] Point{1 x, 2 y} (border-frame float cells),
                            2 type (1 no vacuum, 2 no mop, 3 no entry),
                            3 id, 5 mode (0 region, 1 room) }
    MapOperation_Response { 1 result, 2 map, 3 editVersion, 4 errorCode }

Map and edit version must match the robot's current map (errorCode 1
otherwise), so edits start from a freshly read map. Zones are given in world
metres and sent as border-frame cells; the robot rounds corners to whole
cells (verified). Sent in metres they come out a few centimetres wide, which
the robot rejects with errorCode 9.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .enums import ForbiddenType, ServiceResult, _NamedIntEnum
from .map import ForbiddenArea, MapInfo
from .pb import WIRE_VARINT, Writer, parse

URL_MAP_OPERATION = "/map/operation"

OP_SET = 1
OP_DELETE = 2


class MapEditError(_NamedIntEnum):
    """MapOperation_Response.errorCode (the no-go zone related ones named)."""

    NONE = 0
    UNMATCHED_EDIT_VERSION = 1
    INVALID_ADD_FORBIDDEN_REGION = 9


@dataclass(frozen=True, slots=True)
class NoGoZone:
    """A rectangle to add: two opposite corners in world metres."""

    x1: float
    y1: float
    x2: float
    y2: float
    type: ForbiddenType = ForbiddenType.SWEEP_MOP

    def polygon(self) -> list[tuple[float, float]]:
        left, right = sorted((self.x1, self.x2))
        bottom, top = sorted((self.y1, self.y2))
        if right - left <= 0 or top - bottom <= 0:
            raise ValueError("a no-go zone needs an area")
        return [(left, bottom), (right, bottom), (right, top), (left, top)]


def _forbidden(zone_id: int, kind: int, polygon: Sequence[tuple[float, float]]) -> Writer:
    area = Writer()
    for x, y in polygon:
        area.message(1, Writer().float_(1, x).float_(2, y))
    return area.varint(2, kind).varint(3, zone_id)  # mode 0 (region) is the default


def build_no_go_request(mi: MapInfo, add: Sequence[NoGoZone] = (), delete: Sequence[int] = ()) -> bytes:
    """One MapOperation_Request that adds `add` (new ids after the highest
    existing one) and deletes the zones with the ids in `delete`."""
    if not add and not delete:
        raise ValueError("nothing to change")
    existing = {fa.id: fa for fa in mi.forbiddens}
    if missing := [i for i in delete if i not in existing]:
        raise ValueError(f"no no-go zone with id {missing}")
    req = Writer().varint(1, mi.map_id).varint(2, mi.map_version).varint(3, mi.edit_version)
    next_id = max(existing, default=0) + 1
    for offset, zone in enumerate(add):
        polygon = [mi.world_to_border_point(x, y) for x, y in zone.polygon()]
        op = Writer().varint(1, OP_SET).message(2, _forbidden(next_id + offset, int(zone.type), polygon))
        req.message(4, Writer().message(4, op))
    for zone_id in delete:
        fa: ForbiddenArea = existing[zone_id]
        polygon = [(p.x, p.y) for p in fa.polygon]
        op = Writer().varint(1, OP_DELETE).message(2, _forbidden(zone_id, int(fa.type), polygon))
        req.message(4, Writer().message(4, op))
    return bytes(req)


def decode_map_edit_result(payload: bytes) -> tuple[ServiceResult | int, MapEditError | int]:
    """(result, errorCode) of a MapOperation_Response."""
    result, error = ServiceResult.UNSPECIFIED, MapEditError.NONE
    for f in parse(payload):
        if f.wtype != WIRE_VARINT:
            continue
        if f.num == 1:
            result = ServiceResult.from_value(f.int)
        elif f.num == 4:
            error = MapEditError.from_value(f.int)
    return result, error
