"""Vacuum entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    Segment,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
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

    Rooms of the current map are offered as segments for Home Assistant's
    vacuum.clean_area; the user maps them to Home Assistant areas once.
    """

    _attr_name = None
    _attr_translation_key = "narwal"
    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.LOCATE
        | VacuumEntityFeature.CLEAN_AREA
    )
    _attr_fan_speed_list = list(FAN_SPEEDS.values())

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "vacuum")
        self._segments_issue_for: list[Segment] | None = None

    @property
    def activity(self) -> VacuumActivity:
        return ACTIVITIES[self.coordinator.data.status.activity]

    @property
    def fan_speed(self) -> str | None:
        return FAN_SPEEDS.get(self.coordinator.data.status.fan_level)

    def _segments(self) -> list[Segment]:
        mi = self.coordinator.data.map
        if mi is None:
            return []
        return [Segment(id=str(room.id), name=room.name or str(room.id)) for room in mi.rooms]

    @callback
    def _handle_coordinator_update(self) -> None:
        # Rooms were added, removed or renamed since the user mapped them to
        # areas: ask (once per change) to update the mapping.
        if self.registry_entry is not None and (seen := self.last_seen_segments) is not None:
            current = self._segments()
            if current and current != seen and current != self._segments_issue_for:
                self._segments_issue_for = current
                self.async_create_segments_issue()
        super()._handle_coordinator_update()

    async def async_get_segments(self) -> list[Segment]:
        return self._segments()

    async def async_clean_segments(self, segment_ids: list[str], **kwargs: Any) -> None:
        rooms = [int(segment_id) for segment_id in segment_ids]
        await self._start(rooms)

    async def async_start(self) -> None:
        """Resume a paused clean, otherwise clean every room."""
        if self.coordinator.data.status.activity is Activity.PAUSED:
            await self.coordinator.async_command(self.coordinator.robot.resume())
            await self.coordinator.async_request_refresh()
            return
        await self._start(None)

    async def _start(self, rooms: list[int] | None) -> None:
        await self.coordinator.async_command(
            self.coordinator.robot.start_clean(rooms, mode=self.coordinator.clean_mode)
        )
        await self.coordinator.async_request_refresh()

    async def async_stop(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.robot.stop())
        await self.coordinator.async_request_refresh()

    async def async_locate(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.robot.locate())

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
