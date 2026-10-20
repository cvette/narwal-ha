"""Binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NarwalConfigEntry, NarwalCoordinator, NarwalData
from .entity import NarwalEntity
from .protocol import ChargingStatus

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NarwalBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[NarwalData], bool | None]


BINARY_SENSORS: tuple[NarwalBinarySensorDescription, ...] = (
    NarwalBinarySensorDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.status.charging_status is ChargingStatus.CHARGING,
    ),
    NarwalBinarySensorDescription(
        key="maintenance_needed",
        translation_key="maintenance_needed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: (
            bool(d.consumables.maintain_items or d.consumables.replace_items)
            if d.consumables
            else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(NarwalBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class NarwalBinarySensor(NarwalEntity, BinarySensorEntity):
    entity_description: NarwalBinarySensorDescription

    def __init__(
        self, coordinator: NarwalCoordinator, description: NarwalBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
