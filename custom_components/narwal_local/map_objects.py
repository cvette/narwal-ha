"""Furniture, camera detections and the dock as plain data for attributes."""

from __future__ import annotations

from typing import Any

from .protocol import MapInfo


def type_name(value: Any) -> str:
    """Enum member -> lowercase name; unknown raw ints stay numeric strings."""
    name = getattr(value, "name", None)
    return name.lower() if name else str(value)


def room_name_at(mi: MapInfo, x: float, y: float) -> str | None:
    room_id = mi.room_at(x, y)
    return mi.room_name(room_id) if room_id is not None else None


def furniture_list(mi: MapInfo) -> list[dict[str, Any]]:
    return [
        {"id": f.id, "type": type_name(f.type), "room": room_name_at(mi, f.x, f.y)}
        for f in mi.furniture
    ]


def obstacle_list(mi: MapInfo) -> list[dict[str, Any]]:
    return [
        {"id": o.id, "type": type_name(o.label), "room": room_name_at(mi, o.x, o.y)}
        for o in mi.obstacles
    ]


def dirt_list(mi: MapInfo) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "type": type_name(d.label),
            "status": type_name(d.status),
            "room": room_name_at(mi, d.x, d.y),
        }
        for d in mi.dirt
    ]


def dock_room(mi: MapInfo) -> str | None:
    return room_name_at(mi, mi.station.x, mi.station.y) if mi.station else None
