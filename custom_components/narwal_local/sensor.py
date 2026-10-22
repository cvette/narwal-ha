"""Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .coordinator import NarwalConfigEntry, NarwalCoordinator, NarwalData
from .entity import NarwalEntity
from .map_objects import obstacle_list, obstacle_summary
from .protocol import (
    ERROR_CATEGORIES,
    ChargingStatus,
    TaskType,
    error_category,
    error_hex,
)
from .protocol.enums import (
    BagState,
    CleanWaterTankState,
    DetergentState,
    DustBoxState,
    SewageTankState,
)

PARALLEL_UPDATES = 0

TASK_OPTIONS = [t.name.lower() for t in TaskType if t is not TaskType.UNSPECIFIED]
CHARGING_OPTIONS = [c.name.lower() for c in ChargingStatus if c is not ChargingStatus.UNSPECIFIED]


def _enum_state(value: Any, options: list[str]) -> str | None:
    name = getattr(value, "name", None)
    return name.lower() if name and name.lower() in options else None


def _consumable_attrs(data: NarwalData, items: list[str]) -> dict[str, Any]:
    """Item keys for automations and the reset action, plus readable names."""
    return {"items": items, "names": [data.names.consumable(item) for item in items]}


@dataclass(frozen=True, kw_only=True)
class NarwalSensorDescription(SensorEntityDescription):
    value_fn: Callable[[NarwalData], StateType]
    attrs_fn: Callable[[NarwalData], dict[str, Any] | None] = lambda _: None
    # Created only when the robot reports what the sensor shows.
    exists_fn: Callable[[NarwalData], bool] = lambda _: True


def _options(enum) -> list[str]:
    return [m.name.lower() for m in enum if m.value != 0]


def _station_sensor(key: str, field: int, enum, attr: str) -> NarwalSensorDescription:
    options = _options(enum)
    return NarwalSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENUM,
        options=options,
        value_fn=lambda d: _enum_state(getattr(d.status, attr), options),
        exists_fn=lambda d: d.status.has_field(field),
    )


ERROR_OPTIONS = ["none", *ERROR_CATEGORIES]


def _error_state(d: NarwalData) -> str:
    return error_category(d.status.error_codes[0]) if d.status.error_codes else "none"


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
        key="maintenance_due",
        translation_key="maintenance_due",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.consumables.maintain_items) if d.consumables else None,
        attrs_fn=lambda d: _consumable_attrs(d, d.consumables.maintain_items) if d.consumables else None,
    ),
    NarwalSensorDescription(
        key="replacement_due",
        translation_key="replacement_due",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.consumables.replace_items) if d.consumables else None,
        attrs_fn=lambda d: _consumable_attrs(d, d.consumables.replace_items) if d.consumables else None,
    ),
    NarwalSensorDescription(
        key="detected_obstacles",
        translation_key="detected_obstacles",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.map.obstacles) if d.map else None,
        attrs_fn=lambda d: {"obstacles": obstacle_list(d.map, d.names)} if d.map else None,
    ),
    NarwalSensorDescription(
        key="last_detected",
        translation_key="last_detected",
        value_fn=lambda d: obstacle_summary(d.map, d.names) if d.map else None,
    ),
    NarwalSensorDescription(
        key="error",
        translation_key="error",
        device_class=SensorDeviceClass.ENUM,
        options=ERROR_OPTIONS,
        value_fn=_error_state,
        attrs_fn=lambda d: {
            "codes": [error_hex(c) for c in d.status.error_codes],
            "categories": [error_category(c) for c in d.status.error_codes],
        },
    ),
    _station_sensor("clean_water_tank", 23, CleanWaterTankState, "clean_water"),
    _station_sensor("dirty_water_tank", 24, SewageTankState, "dirty_water"),
    _station_sensor("detergent", 12, DetergentState, "detergent"),
    _station_sensor("dust_box", 20, DustBoxState, "dust_box"),
    _station_sensor("dust_bag", 21, BagState, "dust_bag"),
    _station_sensor("station_bag", 39, BagState, "station_bag"),
    NarwalSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.status.error_codes[0] if d.status.error_codes else 0,
        attrs_fn=lambda d: {"codes": d.status.error_codes},
    ),
)


# From the clean report pushed when a clean finishes; restored after restarts.
LAST_CLEAN_SENSORS: tuple[NarwalSensorDescription, ...] = (
    NarwalSensorDescription(
        key="last_clean_end",
        translation_key="last_clean_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: (
            dt_util.utc_from_timestamp(d.last_report.end)
            if d.last_report and d.last_report.end
            else None
        ),
    ),
    NarwalSensorDescription(
        key="last_clean_area",
        translation_key="last_clean_area",
        device_class=SensorDeviceClass.AREA,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        suggested_display_precision=1,
        value_fn=lambda d: round(d.last_report.area, 2) if d.last_report else None,
    ),
    NarwalSensorDescription(
        key="last_clean_duration",
        translation_key="last_clean_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.last_report.duration if d.last_report else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        NarwalSensor(coordinator, d) for d in SENSORS if d.exists_fn(coordinator.data)
    ]
    entities += [NarwalRestoreSensor(coordinator, d) for d in LAST_CLEAN_SENSORS]
    entities.append(NarwalCurrentRoomSensor(coordinator))
    async_add_entities(entities)


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


class NarwalRestoreSensor(NarwalSensor, RestoreSensor):
    """Keeps its last value across restarts until the robot sends a new one."""

    _restored: StateType | date | datetime | Decimal = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._restored = last.native_value

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        value = self.entity_description.value_fn(self.coordinator.data)
        return value if value is not None else self._restored


class NarwalCurrentRoomSensor(NarwalEntity, SensorEntity):
    """The room the robot is in, from its live position (pushed about once a
    second while it moves) or, when idle, its last saved position. The
    robot's own cleaning_zone_id is not used: it runs ahead through rooms the
    robot is not in."""

    _attr_translation_key = "current_room"

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "current_room")
        self._attr_native_value = self._room()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_live_listener(self._update_room))

    def _room(self) -> str | None:
        mi = self.coordinator.data.map
        if mi is None:
            return None
        pose = self.coordinator.live.robot or mi.robot_pose
        if pose is None:
            return None
        room_id = mi.room_at(pose.x, pose.y)
        return mi.room_name(room_id) if room_id is not None else None

    @callback
    def _update_room(self) -> None:
        room = self._room()
        if room != self._attr_native_value:  # only write when the room changes
            self._attr_native_value = room
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._room()
        super()._handle_coordinator_update()
