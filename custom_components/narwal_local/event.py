"""Event entity: fired when the robot reports the end of a clean."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import CleanReport, ReportTaskType

PARALLEL_UPDATES = 0

EVENT_TYPES = ["completed", "stopped", "interrupted"]

TASK_TYPES: dict[ReportTaskType, str] = {
    ReportTaskType.SWEEP: "vacuum",
    ReportTaskType.MOP: "mop",
    ReportTaskType.SWEEP_MOP: "vacuum_and_mop",
    ReportTaskType.SWEEP_THEN_MOP: "vacuum_then_mop",
    ReportTaskType.SMART: "smart",
    ReportTaskType.CUSTOM: "custom",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NarwalCleanFinishedEvent(entry.runtime_data)])


def _iso(timestamp: int) -> str | None:
    return dt_util.utc_from_timestamp(timestamp).isoformat() if timestamp else None


def event_data(report: CleanReport) -> dict[str, object]:
    result = report.result
    return {
        "result": getattr(result, "name", str(result)).lower(),
        "clean_type": TASK_TYPES.get(report.task_type, "other"),
        "area": round(report.area, 1),
        "duration": report.duration,
        "progress": report.progress,
        "start": _iso(report.start),
        "end": _iso(report.end),
    }


class NarwalCleanFinishedEvent(NarwalEntity, EventEntity):
    """One event per clean report: completed, stopped by someone, or
    interrupted (error, low battery, …), with area and duration."""

    _attr_translation_key = "clean_finished"
    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "clean_finished")
        # Reports from before this entity existed are not replayed.
        self._seen = coordinator.data.last_report if coordinator.data else None

    @callback
    def _handle_coordinator_update(self) -> None:
        report = self.coordinator.data.last_report
        if report is not None and report is not self._seen:
            self._seen = report
            self._trigger_event(report.outcome, event_data(report))
        super()._handle_coordinator_update()
