"""Number entities: the voice volume."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import Setting

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.data.config is not None:
        async_add_entities([NarwalVolume(coordinator)])


class NarwalVolume(NarwalEntity, NumberEntity):
    _attr_translation_key = "volume"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "volume")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.config is not None

    @property
    def native_value(self) -> int | None:
        config = self.coordinator.data.config
        return config.volume if config else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_config(Setting.VOLUME, round(value))
