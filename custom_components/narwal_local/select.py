"""Select entities."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import CleanMode, CornerCleaning, MopHumidity, Setting
from .protocol.config import SETTINGS

PARALLEL_UPDATES = 1

MOP_OPTIONS: dict[MopHumidity, str] = {
    MopHumidity.DRY: "dry",
    MopHumidity.NORMAL: "normal",
    MopHumidity.WET: "wet",
}
MOP_LEVELS = {name: level for level, name in MOP_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        NarwalMopHumiditySelect(coordinator),
        NarwalCleanModeSelect(coordinator),
    ]
    if (config := coordinator.data.config) is not None:
        features = coordinator.static.features
        entities.extend(
            NarwalSettingSelect(coordinator, d)
            for d in SETTING_SELECTS
            if (d.feature is None or features.supports(d.feature)) and config.has(d.setting)
        )
    async_add_entities(entities)


class NarwalMopHumiditySelect(NarwalEntity, SelectEntity):
    _attr_translation_key = "mop_humidity"
    _attr_options = list(MOP_OPTIONS.values())

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "mop_humidity")

    @property
    def current_option(self) -> str | None:
        return MOP_OPTIONS.get(self.coordinator.data.status.mop_humidity)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_command(
            self.coordinator.robot.set_mop_humidity(MOP_LEVELS[option])
        )
        await self.coordinator.async_request_refresh()


CLEAN_MODE_OPTIONS: dict[CleanMode, str] = {
    CleanMode.SWEEP_MOP: "vacuum_and_mop",
    CleanMode.SWEEP: "vacuum",
    CleanMode.MOP: "mop",
    CleanMode.SWEEP_THEN_MOP: "vacuum_then_mop",
}
CLEAN_MODES = {name: mode for mode, name in CLEAN_MODE_OPTIONS.items()}


class NarwalCleanModeSelect(NarwalEntity, SelectEntity, RestoreEntity):
    """How cleans started from Home Assistant run. The robot has no current
    mode of its own (the app picks one per clean), so it is kept here and
    restored after restarts."""

    _attr_translation_key = "clean_mode"
    _attr_options = list(CLEAN_MODE_OPTIONS.values())

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "clean_mode")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None and last.state in CLEAN_MODES:
            self.coordinator.clean_mode = CLEAN_MODES[last.state]

    @property
    def current_option(self) -> str:
        return CLEAN_MODE_OPTIONS[self.coordinator.clean_mode]

    async def async_select_option(self, option: str) -> None:
        self.coordinator.clean_mode = CLEAN_MODES[option]
        self.async_write_ha_state()


@dataclass(frozen=True, kw_only=True)
class NarwalSettingSelectDescription(SelectEntityDescription):
    setting: Setting
    feature: str | None = None  # feature flag the robot must report
    # Option -> feature flag it needs, for options only some robots have.
    option_features: dict[str, str] | None = None


SETTING_SELECTS: tuple[NarwalSettingSelectDescription, ...] = (
    NarwalSettingSelectDescription(
        key="carpet_strategy", setting=Setting.CARPET_STRATEGY, feature="supportCarpetCleanSetting"
    ),
    NarwalSettingSelectDescription(key="mop_drying", setting=Setting.MOP_DRYING),
    NarwalSettingSelectDescription(key="mop_wash_frequency", setting=Setting.MOP_WASH_FREQUENCY),
    NarwalSettingSelectDescription(
        key="corner_cleaning",
        setting=Setting.CORNER_CLEANING,
        feature="supportCornerClean",
        option_features={CornerCleaning.FLEXIBLE_MOP.name.lower(): "supportFlexibleMop"},
    ),
    NarwalSettingSelectDescription(
        key="obstacle_avoidance", setting=Setting.OBSTACLE_AVOIDANCE, feature="supportAvoidModeConfig"
    ),
)


class NarwalSettingSelect(NarwalEntity, SelectEntity):
    """A robot setting with several options; the option keys are the enum's
    member names in lowercase."""

    _attr_entity_category = EntityCategory.CONFIG
    entity_description: NarwalSettingSelectDescription

    def __init__(
        self, coordinator: NarwalCoordinator, description: NarwalSettingSelectDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._enum = SETTINGS[description.setting].enum
        features = coordinator.static.features
        needs = description.option_features or {}
        options = [member.name.lower() for member in self._enum if member.value]
        self._attr_options = [
            option for option in options if option not in needs or features.supports(needs[option])
        ]

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.config is not None

    @property
    def current_option(self) -> str | None:
        if (config := self.coordinator.data.config) is None:
            return None
        value = config.options.get(self.entity_description.setting)
        name = getattr(value, "name", None)
        return name.lower() if name and name.lower() in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_config(
            self.entity_description.setting, self._enum[option.upper()]
        )
