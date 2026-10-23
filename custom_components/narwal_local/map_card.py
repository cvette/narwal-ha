"""Backend of the interactive map card (www/narwal-map-card.js).

The card asks for the map over Home Assistant's websocket API: the base map
as a PNG (rooms, walls, icons and labels, without the robot), the transform
from map metres to image pixels, the rooms, a room-id grid for tapping rooms,
and the current clean's path. Everything that moves (robot, path, zones being
drawn) the card draws itself; the robot's position comes from
sensor.narwal_position.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .protocol.card import build_map_payload, map_version

CARD_FILE = Path(__file__).parent / "www" / "narwal-map-card.js"
CARD_URL = f"/{DOMAIN}/narwal-map-card.js"
_CACHE_KEY = f"{DOMAIN}_map_card_cache"


def _path_in_metres(coordinator: NarwalCoordinator) -> list[list[float]]:
    mi = coordinator.data.map
    if mi is None:
        return []
    out = []
    for x, y in coordinator.live.path:
        c = mi.border_point_to_cell(x, y)
        w = mi.cell_to_world(c.col, c.row)
        out.append([round(w.x, 3), round(w.y, 3)])
    return out


def _coordinator_for(hass: HomeAssistant, entity_id: str) -> NarwalCoordinator | None:
    entry_id = (ent := er.async_get(hass).async_get(entity_id)) and ent.config_entry_id
    entry: NarwalConfigEntry | None = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        return None
    return entry.runtime_data


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/map",
        vol.Required("entity_id"): str,
        vol.Optional("version"): str,
    }
)
@websocket_api.async_response
async def ws_map(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The card's map for a Narwal entity (usually the vacuum). With the
    `version` the card already has, only the path is sent unless the map
    changed."""
    coordinator = _coordinator_for(hass, msg["entity_id"])
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "Not a loaded Narwal Local entity")
        return
    mi = coordinator.data.map
    if mi is None or not mi.robot_has_map:
        connection.send_error(msg["id"], "no_map", "The robot has no map yet")
        return
    registry = er.async_get(hass)
    result: dict[str, Any] = {
        "path": _path_in_metres(coordinator),
        "position_entity": registry.async_get_entity_id(
            "sensor", DOMAIN, f"{coordinator.device_id}_position"
        ),
        "vacuum_entity": registry.async_get_entity_id(
            "vacuum", DOMAIN, f"{coordinator.device_id}_vacuum"
        ),
        "battery_entity": registry.async_get_entity_id(
            "sensor", DOMAIN, f"{coordinator.device_id}_battery"
        ),
    }
    version = map_version(mi)
    if msg.get("version") == version:
        result["version"] = version
    else:
        cache: dict[str, tuple[str, dict[str, Any]]] = hass.data.setdefault(_CACHE_KEY, {})
        cached = cache.get(coordinator.config_entry.entry_id)
        if cached is None or cached[0] != version:
            cached = (version, await hass.async_add_executor_job(build_map_payload, mi))
            cache[coordinator.config_entry.entry_id] = cached
        result |= cached[1]
    connection.send_result(msg["id"], result)


async def async_setup_card(hass: HomeAssistant) -> None:
    """Serve the card and load it on every dashboard (once per start). The
    version in the URL makes browsers fetch the card again after an update."""
    websocket_api.async_register_command(hass, ws_map)
    if hass.http is not None:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
        )
    if "frontend" in hass.config.components:
        version = (await async_get_integration(hass, DOMAIN)).version
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")


@callback
def async_forget_map(hass: HomeAssistant, entry_id: str) -> None:
    hass.data.get(_CACHE_KEY, {}).pop(entry_id, None)
