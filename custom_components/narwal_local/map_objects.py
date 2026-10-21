"""Furniture, camera detections and the dock as plain data for attributes,
with display names in Home Assistant's language."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN
from .protocol import MapInfo


def type_name(value: Any) -> str:
    """Enum member -> lowercase name; unknown raw ints stay numeric strings."""
    name = getattr(value, "name", None)
    return name.lower() if name else str(value)


@dataclass(frozen=True, slots=True)
class ObjectNames:
    """Display names from the `selector` translations, keyed by type name.
    A missing name falls back to the type key itself."""

    obstacles: dict[str, str] = field(default_factory=dict)
    furniture: dict[str, str] = field(default_factory=dict)
    dirt: dict[str, str] = field(default_factory=dict)

    def obstacle(self, label: Any) -> str:
        key = type_name(label)
        return self.obstacles.get(key, key)

    def furniture_name(self, ftype: Any) -> str:
        key = type_name(ftype)
        return self.furniture.get(key, key)

    def dirt_name(self, label: Any) -> str:
        key = type_name(label)
        return self.dirt.get(key, key)

    @property
    def none(self) -> str:
        return self.obstacles.get("none", "none")


async def async_load_names(hass: HomeAssistant) -> ObjectNames:
    """Load names in the configured language (English fills any gaps)."""
    strings = await async_get_translations(hass, hass.config.language, "selector", {DOMAIN})

    def table(kind: str) -> dict[str, str]:
        prefix = f"component.{DOMAIN}.selector.{kind}.options."
        return {k.removeprefix(prefix): v for k, v in strings.items() if k.startswith(prefix)}

    return ObjectNames(table("obstacle_type"), table("furniture_type"), table("dirt_type"))


def room_name_at(mi: MapInfo, x: float, y: float) -> str | None:
    room_id = mi.room_at(x, y)
    return mi.room_name(room_id) if room_id is not None else None


def furniture_list(mi: MapInfo, names: ObjectNames) -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "type": type_name(f.type),
            "name": names.furniture_name(f.type),
            "room": room_name_at(mi, f.x, f.y),
        }
        for f in mi.furniture
    ]


def obstacle_list(mi: MapInfo, names: ObjectNames) -> list[dict[str, Any]]:
    return [
        {
            "id": o.id,
            "type": type_name(o.label),
            "name": names.obstacle(o.label),
            "room": room_name_at(mi, o.x, o.y),
        }
        for o in mi.obstacles
    ]


def dirt_list(mi: MapInfo, names: ObjectNames) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "type": type_name(d.label),
            "name": names.dirt_name(d.label),
            "status": type_name(d.status),
            "room": room_name_at(mi, d.x, d.y),
        }
        for d in mi.dirt
    ]


def obstacle_summary(mi: MapInfo, names: ObjectNames) -> str:
    """"3× Kabel, 2× Schuhe, 1× Plastiktüte": most frequent first, at most
    255 characters (a state's limit)."""
    counts = Counter(names.obstacle(o.label) for o in mi.obstacles)
    if not counts:
        return names.none
    parts = [f"{n}× {name}" for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    text = ", ".join(parts)
    return text if len(text) <= 255 else text[:254] + "…"


def dock_room(mi: MapInfo) -> str | None:
    return room_name_at(mi, mi.station.x, mi.station.y) if mi.station else None
