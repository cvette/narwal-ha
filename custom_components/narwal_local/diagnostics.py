"""Diagnostics download."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import NarwalConfigEntry
from .map_objects import dirt_list, furniture_list, obstacle_list

TO_REDACT = {"token", "device_id", "binded_uuid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NarwalConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    static = coordinator.static
    status = asdict(data.status)
    status["activity"] = str(data.status.activity)
    status["task"] = getattr(data.status.task, "name", data.status.task)
    mi = data.map
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "connected": coordinator.robot.connected,
            "device": asdict(static.device),
            "firmware": asdict(static.firmware) if static.firmware else None,
            "features": {"enabled": static.features.enabled, "other": static.features.other},
            "status": status,
            "working": asdict(data.working) if data.working else None,
            "consumables": asdict(data.consumables) if data.consumables else None,
            "map": {
                "ref": mi.ref,
                "size": [mi.width, mi.height],
                "resolution_mm": mi.resolution_mm,
                "rooms": [{"id": r.id, "name": r.name} for r in mi.rooms],
                "doors": len(mi.doors),
                "carpets": len(mi.carpets),
                "forbiddens": len(mi.forbiddens),
                "station": asdict(mi.station) if mi.station else None,
                "furniture": furniture_list(mi),
                "obstacles": obstacle_list(mi),
                "dirt": dirt_list(mi),
            }
            if mi
            else None,
        },
        TO_REDACT,
    )
