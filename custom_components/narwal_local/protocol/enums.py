"""Enum values recovered from app_protol (Narwal app 2.9.90)."""

from __future__ import annotations

from enum import IntEnum


class _NamedIntEnum(IntEnum):
    @classmethod
    def from_value(cls, value: int):
        """Return the member, or the raw int when the robot sends a newer value."""
        try:
            return cls(value)
        except ValueError:
            return value


class FanLevel(_NamedIntEnum):
    """SetFanLevel.level / RobotBaseStatus.fanLevel."""

    UNSPECIFIED = 0
    MUTE = 1
    NORMAL = 2
    STRONG = 3
    DEEP = 4
    SUPER = 5


class MopHumidity(_NamedIntEnum):
    """SetMopHumidity.mopHumidity / RobotBaseStatus.mopHumidity."""

    UNSPECIFIED = 0
    DRY = 1
    NORMAL = 2
    WET = 3


class ForbiddenType(_NamedIntEnum):
    """ForbiddenArea.type."""

    UNSPECIFIED = 0
    SWEEP = 1  # no sweeping
    MOP = 2  # no mopping
    SWEEP_MOP = 3  # no entry at all


class FirmwareStatus(_NamedIntEnum):
    """CheckFirmware_Response.firmwareStatus."""

    UNSPECIFIED = 0
    NO_PACKAGE = 1
    DOWNLOADED = 2  # the robot already fetched an update and can install it


class ChargingStatus(_NamedIntEnum):
    """RobotBaseStatus.chargingStatus (field 47)."""

    UNSPECIFIED = 0
    CHARGING = 1
    DISCHARGING = 2
    NOT_CHARGING = 3  # seen docked at 100 % in standby
    FULL = 4
    BATTERY_PROTECT = 5


class TaskType(_NamedIntEnum):
    """RobotTaskStatus.task (RobotBaseStatus field 3, sub-field 1)."""

    UNSPECIFIED = 0
    IDLE = 1
    SWEEP = 2
    MOP = 3
    SWEEP_THEN_MOP = 4
    SWEEP_AND_MOP = 5
    SMART_CLEAN = 6
    BUILD_MAP = 7
    PARKING = 8
    DEPARTURE = 9
    RECALL = 10
    NET_CONFIG = 11
    UPGRADE = 12
    RELOCALIZATION = 13
    WASH_AND_DRY_MOP = 14
    PAIRING = 15
    UPDATE_MAP = 16
    COMPOSITE_CLEAN = 17
    DEBUG = 18
    DUST_GATHERING = 19
    DRY_STATION_BAG = 20
    TELECONTROL = 21
    MAINTAIN_FLOOR = 22
    SEARCH_PERSON = 23
    VIDEO_CRUISE = 24
    PUMP_TROUBLESHOOTING = 25
    ROBOT_SEWAGE_BOX_PUMP_TROUBLESHOOTING = 26
    SEARCH_PET = 27


class IdleStatus(_NamedIntEnum):
    """RobotTaskStatus.idleStatus (sub-field 3)."""

    UNSPECIFIED = 0
    IN_STATION = 1
    OUTSIDE_STATION = 2
    UNINSTALLED_CLEAN_MODULE = 3
    UNINSTALLED_SWEEP_MODULE = 4
    UNINSTALLED_MOP_MODULE = 5
    LOW_POWER_IN_STATION = 6  # seen docked at 100 %: standby, not low battery
    LOW_POWER_OUTSIDE_STATION = 7


class ServiceResult(_NamedIntEnum):
    """The common response result enum (field 1 of most responses)."""

    UNSPECIFIED = 0
    PERFORM_SUCCESS = 1
    PERFORM_GENERAL_FAILED = 2
    ALREADY_EXECUTING = 3
    POWER_LOWER = 4
    ROBOT_TRAPPED_IN_STATION = 5
    ROBOT_IN_STATION_WHEN_RECALL = 6
    ROBOT_NOT_IN_STATION_WHEN_BUILD_MAP = 7
    ROBOT_NOT_CONTACT_WITH_STATION = 8
    DUST_BOX_NOT_INSTALLED = 9
    MOP_NOT_INSTALLED = 10
    FORBIDDEN_TASK_IN_NET_CONFIG = 11
    FORBIDDEN_TASK_IN_UPGRADE = 12
    FORBIDDEN_TASK_IN_BLUETOOTH_PAIRING = 13
    FORBIDDEN_TASK_IN_AUTO_WATER_SELF_CHECK = 14
    FORBIDDEN_RECALL_IN_RE_LOCALIZATION = 15
    FORBIDDEN_TASK_IF_NOT_ACTIVATED = 16
    FORBIDDEN_TASK_IF_STATION_NOT_CONNECTED = 17
    FORBIDDEN_TASK_IF_CAN_NOT_REACH_SPECIFIED_AREA = 18
    FORBIDDEN_TASK_WHEN_CHARGE = 19
    FORBIDDEN_RECALL_WHEN_NO_MAP = 20
    LIDAR_CALIBRATION_SUCCESS = 21
    NO_NEED_UPDATE_MAP = 22
    NOT_IN_MAIN_MAP = 23
    NO_STATION_IN_MAP = 24
    FORBIDDEN_TASK_IF_STATION_IN_CERTIFICATION = 25
    UPPER_COVER_NOT_INSTALLED = 26
    STATION_BAG_UNINSTALL = 27
    IN_TELECONTROL = 28
    FORBIDDEN_IN_SECOND_CLEAN = 29
    FAILED_DURING_MOTOR_COOLING = 30
    STATION_LIGHT_CTRL_FAILED = 31
    STATION_LIGHT_CTRL_TIMEOUT = 32


# Consumable enums; short names drop the CONSUMABLE_{MAINTAIN,REPLACE}_ITEM_ prefix.
MAINTAIN_ITEM_NAMES: dict[int, str] = {
    0: "unspecified", 1: "dust_box", 2: "dust_filter", 3: "dirty_water",
    4: "wash_ribs", 5: "smart_module_filter", 6: "universal_wheel",
    7: "cliff_sensor", 8: "side_distance_sensor", 9: "water_tank_sponge",
    10: "anti_winding_brush", 11: "smart_module_sponge", 20: "dust_container",
}  # fmt: skip

REPLACE_ITEM_NAMES: dict[int, str] = {
    0: "unspecified", 1: "dust_filter", 2: "mop", 3: "side_brush",
    4: "clear_water_filter", 5: "roller_brush", 6: "detergent",
    7: "smart_module_filter", 8: "dust_bag", 20: "station_bag",
    21: "silver_ions", 22: "curing_agent", 23: "heavy_detergent",
    24: "inner_dust_box",
}  # fmt: skip
