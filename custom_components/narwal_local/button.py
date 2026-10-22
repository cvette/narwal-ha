"""Buttons for the station's actions: empty the dust box, wash or dry the mop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import NarwalRobot

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class NarwalButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[NarwalRobot], Awaitable[None]]


BUTTONS: tuple[NarwalButtonDescription, ...] = (
    NarwalButtonDescription(key="empty_dust_bin", press_fn=lambda r: r.empty_dust_bin()),
    NarwalButtonDescription(key="wash_mop", press_fn=lambda r: r.wash_mop()),
    NarwalButtonDescription(key="dry_mop", press_fn=lambda r: r.dry_mop()),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.data.status.has_station:
        async_add_entities(NarwalStationButton(coordinator, d) for d in BUTTONS)


class NarwalStationButton(NarwalEntity, ButtonEntity):
    """Starts a station action; the robot must be docked. Stop it with the
    vacuum's stop, like any task."""

    entity_description: NarwalButtonDescription

    def __init__(self, coordinator: NarwalCoordinator, description: NarwalButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    async def async_press(self) -> None:
        await self.coordinator.async_command(self.entity_description.press_fn(self.coordinator.robot))
        await self.coordinator.async_request_refresh()
