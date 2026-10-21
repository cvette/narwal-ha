"""Switches for the robot's on/off settings."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import Setting

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class NarwalSwitchDescription(SwitchEntityDescription):
    setting: Setting
    feature: str | None = None  # feature flag the robot must report


SWITCHES: tuple[NarwalSwitchDescription, ...] = (
    NarwalSwitchDescription(key="do_not_disturb", setting=Setting.DO_NOT_DISTURB),
    NarwalSwitchDescription(key="child_lock", setting=Setting.CHILD_LOCK),
    NarwalSwitchDescription(key="dust_gathering", setting=Setting.DUST_GATHERING),
    NarwalSwitchDescription(
        key="quiet_dust_gathering",
        setting=Setting.QUIET_DUST_GATHERING,
        feature="supportQuietDustGathering",
    ),
    NarwalSwitchDescription(key="dry_dust_bag", setting=Setting.DRY_DUST_BAG),
    NarwalSwitchDescription(key="auto_add_detergent", setting=Setting.AUTO_ADD_DETERGENT),
    NarwalSwitchDescription(
        key="hot_water_wash", setting=Setting.HOT_WATER_WASH, feature="supportHotWaterWash"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.data.config is None:
        return
    features = coordinator.static.features
    async_add_entities(
        NarwalSettingSwitch(coordinator, d)
        for d in SWITCHES
        if d.feature is None or features.supports(d.feature)
    )


class NarwalSettingSwitch(NarwalEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG
    entity_description: NarwalSwitchDescription

    def __init__(self, coordinator: NarwalCoordinator, description: NarwalSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.config is not None

    @property
    def is_on(self) -> bool | None:
        if (config := self.coordinator.data.config) is None:
            return None
        if self.entity_description.setting is Setting.DO_NOT_DISTURB:
            return config.do_not_disturb.enabled
        return config.flags.get(self.entity_description.setting)

    async def _async_set(self, on: bool) -> None:
        setting = self.entity_description.setting
        value: Any = on
        if setting is Setting.DO_NOT_DISTURB:
            # The whole DisturbMode is written; keep the robot's times.
            value = replace(self.coordinator.data.config.do_not_disturb, enabled=on)
        await self.coordinator.async_set_config(setting, value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
