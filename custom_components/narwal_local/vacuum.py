"""Vacuum entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import Activity, FanLevel

PARALLEL_UPDATES = 1

FAN_SPEEDS: dict[FanLevel, str] = {
    FanLevel.MUTE: "mute",
    FanLevel.NORMAL: "normal",
    FanLevel.STRONG: "strong",
    FanLevel.DEEP: "deep",
    FanLevel.SUPER: "super",
}
FAN_LEVELS = {name: level for level, name in FAN_SPEEDS.items()}

ACTIVITIES: dict[Activity, VacuumActivity] = {
    Activity.CLEANING: VacuumActivity.CLEANING,
    Activity.DOCKED: VacuumActivity.DOCKED,
    Activity.IDLE: VacuumActivity.IDLE,
    Activity.PAUSED: VacuumActivity.PAUSED,
    Activity.RETURNING: VacuumActivity.RETURNING,
    Activity.ERROR: VacuumActivity.ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NarwalVacuum(entry.runtime_data)])


class NarwalVacuum(NarwalEntity, StateVacuumEntity):
    """The robot itself.

    START only resumes a paused task for now: starting a new clean has not been
    verified on a robot yet.
    """

    _attr_name = None
    _attr_translation_key = "narwal"
    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
    )
    _attr_fan_speed_list = list(FAN_SPEEDS.values())

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "vacuum")

    @property
    def activity(self) -> VacuumActivity:
        return ACTIVITIES[self.coordinator.data.status.activity]

    @property
    def fan_speed(self) -> str | None:
        return FAN_SPEEDS.get(self.coordinator.data.status.fan_level)

    async def async_start(self) -> None:
        if self.coordinator.data.status.activity is not Activity.PAUSED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="start_not_supported"
            )
        await self.coordinator.async_command(self.coordinator.robot.resume())
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        await self.coordinator.async_command(self.coordinator.robot.pause())
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.robot.dock())
        await self.coordinator.async_request_refresh()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        if (level := FAN_LEVELS.get(fan_speed)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_fan_speed",
                translation_placeholders={"fan_speed": fan_speed},
            )
        await self.coordinator.async_command(self.coordinator.robot.set_fan_level(level))
        await self.coordinator.async_request_refresh()
