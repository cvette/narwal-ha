"""Select entities."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import CleanMode, MopHumidity

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
    async_add_entities([NarwalMopHumiditySelect(coordinator), NarwalCleanModeSelect(coordinator)])


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
