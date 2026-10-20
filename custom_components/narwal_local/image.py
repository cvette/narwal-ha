"""The map as an image entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .map_objects import dirt_list, dock_room, furniture_list, obstacle_list
from .protocol import MapInfo, add_room_labels, render_png

PARALLEL_UPDATES = 0

MAP_SCALE = 4  # pixels per map cell


def render_map(mi: MapInfo) -> bytes:
    """Render with room names. CPU-bound: call it in the executor."""
    png, viewport = render_png(mi, MAP_SCALE)
    return add_room_labels(png, mi, viewport)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NarwalMapImage(hass, entry.runtime_data)])


class NarwalMapImage(NarwalEntity, ImageEntity):
    """Rooms, walls, doors, carpets, no-go zones, furniture, camera
    detections and the dock.

    The PNG is rendered on first request after the map changed and cached; a
    map counts as changed when its id, version, edit version, room names,
    furniture, detections or dock change.
    """

    _attr_translation_key = "map"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, coordinator: NarwalCoordinator) -> None:
        NarwalEntity.__init__(self, coordinator, "map")
        ImageEntity.__init__(self, hass)
        self._map_key = self._current_key()
        self._png: bytes | None = None
        if self._map_key is not None:
            self._attr_image_last_updated = dt_util.utcnow()

    def _current_key(self) -> tuple | None:
        mi = self.coordinator.data.map
        if mi is None or not mi.robot_has_map:
            return None
        return (
            mi.ref,
            tuple((r.id, r.name) for r in mi.rooms),
            tuple(mi.furniture),
            tuple(mi.obstacles),
            tuple(mi.dirt),
            mi.station,
        )

    @property
    def available(self) -> bool:
        return super().available and self._map_key is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        key = self._current_key()
        if key != self._map_key:
            self._map_key = key
            self._png = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        mi = self.coordinator.data.map
        if mi is None or self._map_key is None:
            return None
        if self._png is None:
            self._png = await self.hass.async_add_executor_job(render_map, mi)
        return self._png

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        mi = self.coordinator.data.map
        if mi is None:
            return None
        return {
            "map_id": mi.map_id,
            "rooms": [{"id": r.id, "name": r.name} for r in mi.rooms],
            "dock_room": dock_room(mi),
            "furniture": furniture_list(mi),
            "obstacles": obstacle_list(mi),
            "dirt": dirt_list(mi),
        }
