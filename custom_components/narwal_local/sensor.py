"""Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import NarwalConfigEntry, NarwalCoordinator, NarwalData
from .entity import NarwalEntity
from .protocol import ChargingStatus, TaskType

PARALLEL_UPDATES = 0

TASK_OPTIONS = [t.name.lower() for t in TaskType if t is not TaskType.UNSPECIFIED]
CHARGING_OPTIONS = [c.name.lower() for c in ChargingStatus if c is not ChargingStatus.UNSPECIFIED]


def _enum_state(value: Any, options: list[str]) -> str | None:
    name = getattr(value, "name", None)
    return name.lower() if name and name.lower() in options else None


def _current_room(data: NarwalData) -> str | None:
    if data.working is None or data.map is None or not data.working.cleaning_zone_id:
        return None
    return data.map.room_name(data.working.cleaning_zone_id)


@dataclass(frozen=True, kw_only=True)
class NarwalSensorDescription(SensorEntityDescription):
    value_fn: Callable[[NarwalData], StateType]
    attrs_fn: Callable[[NarwalData], dict[str, Any] | None] = lambda _: None


SENSORS: tuple[NarwalSensorDescription, ...] = (
    NarwalSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: round(d.status.battery),
    ),
    NarwalSensorDescription(
        key="task",
        translation_key="task",
        device_class=SensorDeviceClass.ENUM,
        options=TASK_OPTIONS,
        value_fn=lambda d: _enum_state(d.status.task, TASK_OPTIONS),
    ),
    NarwalSensorDescription(
        key="charging_status",
        translation_key="charging_status",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGING_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _enum_state(d.status.charging_status, CHARGING_OPTIONS),
    ),
    NarwalSensorDescription(
        key="cleaning_progress",
        translation_key="cleaning_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.working.working_progress if d.working else None,
    ),
    NarwalSensorDescription(
        key="cleaned_area",
        translation_key="cleaned_area",
        device_class=SensorDeviceClass.AREA,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.working.covered_area if d.working else None,
    ),
    NarwalSensorDescription(
        key="cleaning_time",
        translation_key="cleaning_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.working.time_consuming if d.working else None,
    ),
    NarwalSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.working.remained_time if d.working else None,
    ),
    NarwalSensorDescription(
        key="current_room",
        translation_key="current_room",
        value_fn=_current_room,
    ),
    NarwalSensorDescription(
        key="maintenance_due",
        translation_key="maintenance_due",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.consumables.maintain_items) if d.consumables else None,
        attrs_fn=lambda d: {"items": d.consumables.maintain_items} if d.consumables else None,
    ),
    NarwalSensorDescription(
        key="replacement_due",
        translation_key="replacement_due",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.consumables.replace_items) if d.consumables else None,
        attrs_fn=lambda d: {"items": d.consumables.replace_items} if d.consumables else None,
    ),
    NarwalSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.status.error_codes[0] if d.status.error_codes else 0,
        attrs_fn=lambda d: {"codes": d.status.error_codes},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(NarwalSensor(coordinator, description) for description in SENSORS)


class NarwalSensor(NarwalEntity, SensorEntity):
    entity_description: NarwalSensorDescription

    def __init__(self, coordinator: NarwalCoordinator, description: NarwalSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.coordinator.data)
