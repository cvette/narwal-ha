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


class ReportTaskType(_NamedIntEnum):
    """CleanReportSubmit.taskType (field 5): what kind of clean it was."""

    UNSPECIFIED = 0
    SWEEP = 1
    MOP = 2
    SWEEP_MOP = 3  # vacuum and mop together
    SWEEP_THEN_MOP = 4
    SMART = 5
    CUSTOM = 6  # rooms with their own parameters, as Home Assistant starts them


class TaskResult(_NamedIntEnum):
    """CleanReportSubmit.taskRes (field 8): how the task ended."""

    UNSPECIFIED = 0
    NORMAL_END = 1
    USER_FORCE_END = 2
    SHUTDOWN_FORCE_END = 3
    LOW_BATTERY_FORCE_END = 4
    OVERFLOW_FORCE_END = 5
    PAUSE_TOO_LONG_FORCE_END = 6
    SYSTEM_ERROR_FORCE_END = 7
    USER_FORCE_END_ON_STATION = 8
    USER_FORCE_END_ON_APP = 9
    RECALL_END = 10
    NORMAL_END_WITH_REPLENISH_MAP_FAIL = 11
    MAP_UNMATCHED_FORCE_END = 12
    RELOCATION_FAIL_WITH_STATION = 13
    RELOCATION_FAIL_WITHOUT_STATION = 14
    PRETASK_ERROR_FORCE_END = 15
    SCHEDULE_TASK_FORCE_END = 16
    UNEXECUTED = 17
    PET_NOT_FOUND = 18


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


class FurnitureType(_NamedIntEnum):
    """Furniture.furnitureType (MapBaseType). The app spells CLOSESTOOL and
    REFRIGERTOR; renamed here to TOILET and REFRIGERATOR."""

    UNSPECIFIED = 0
    SINGLE_BED = 1
    DOUBLE_BED = 2
    BABY_BED = 3
    DINNER_TABLE_SQUARE = 4
    DINNER_TABLE_ROUND = 5
    TEA_TABLE_SQUARE = 6
    TEA_TABLE_ROUND = 7
    TV_CUPBOARD = 8
    BEDSIDE_TABLE = 9
    LOCKER = 10
    WARDROBE = 11
    SHOE_CUPBOARD = 12
    SOFA_SINGLE = 13
    SOFA_MULTI = 14
    SOFA_L_SHAPE = 15
    SOFA_LAZY = 16
    CHAIR = 17
    BAR_CHAIR = 18
    CAT_TOILET = 19
    PET_EATING_AREA = 20
    PET_HOUSE = 21
    WASHING_MACHINE = 22
    REFRIGERATOR = 23
    VERTICAL_AIRCON = 24
    VERTICAL_FAN = 25
    POTTED_PLANT = 26
    FLOOR_MIRROR = 27
    TOILET = 28
    PIANO = 29
    SOFA_U_SHAPE = 30
    DESK = 31
    GRAND_PIANO = 32
    WASHBASIN = 33
    COOKER_HOOD_STOVE = 34
    WINE_CABINET = 74
    CAT_HOUSE = 75
    DOG_HOUSE = 76
    ROUND_PLACEHOLDER = 77
    WEIGHING_SCALE = 78


class ObstacleLabel(_NamedIntEnum):
    """VisionObs.label: objects the camera recognised during a clean."""

    UNSPECIFIED = 0
    CABLE = 1
    TISSUE = 2
    POOP = 3
    LIQUID = 4
    SHOES = 5
    SOLID = 6
    SOCKS = 7
    PLASTIC_BAG = 8
    TRASH_BIN = 9
    NORMAL = 10
    UNCLEANABLE = 11
    TEXTILES = 12
    NOT_EXIST = 13
    GROUND_TEXTURE = 14
    PET = 15
    CLIFF = 16
    SQUATTING_WC = 17
    CHAIR_U_LEGS = 18
    CHAIR_WHEEL = 19
    FLOOR_MIRROR = 20
    BOOK = 21
    STICK = 22
    MERGE_FLEXIBLE = 23
    JEWELRY = 24
    PHONE = 25
    WALLET = 26
    KEY = 27
    BANKNOTE = 28
    REMOTE_CONTROL = 29
    GLASSES = 30
    WATCH = 31
    CARD = 32
    HEADPHONES = 33
    BABY_TOY = 34
    PLANT = 35
    FITNESS_EQUIPMENT = 36
    PET_TOY = 37
    DANGEROUS_GOODS = 38
    DECORATION = 39
    PAPER_BOX = 40
    PET_CAT = 41
    PET_DOG = 42


class DirtLabel(_NamedIntEnum):
    """VisionDirty.label."""

    UNSPECIFIED = 0
    LIQUID_MANY = 1
    SOLID_MANY = 2
    LIQUID_MASSIVE = 3
    SOLID_MASSIVE = 4


class DirtStatus(_NamedIntEnum):
    """VisionDirty.status."""

    EXPLORING = 0
    CLEANING = 1
    CLEANED = 2


# --- Station and robot tank states (RobotBaseStatus) ----------------------------


class CleanWaterTankState(_NamedIntEnum):
    """Field 23."""

    UNSPECIFIED = 0
    NORMAL = 1
    EMPTY = 2
    NOT_INSTALLED = 3
    ABNORMAL = 4


class SewageTankState(_NamedIntEnum):
    """Field 24: the dirty water tank. The robot cannot tell full from missing."""

    UNSPECIFIED = 0
    NORMAL = 1
    FULL_OR_MISSING = 2
    ABNORMAL = 3


class DetergentState(_NamedIntEnum):
    """Field 12."""

    UNSPECIFIED = 0
    OK = 1
    NOT_INSTALLED = 2
    EMPTY = 3
    RUNNING_OUT = 4
    NOT_USED = 5


class DustBoxState(_NamedIntEnum):
    """Field 20."""

    UNSPECIFIED = 0
    NORMAL = 1
    NOT_INSTALLED = 2
    ABNORMAL = 3
    CLEAN_SUGGESTED = 4


class BagState(_NamedIntEnum):
    """Field 21 (robot dust bag) uses 1 normal, 2 missing, 3 replace, 4 fault;
    field 39 (station dust bag) uses 1 installed, 2 missing, 3 replace,
    4 fault, so one enum serves both."""

    UNSPECIFIED = 0
    OK = 1
    NOT_INSTALLED = 2
    REPLACE_SUGGESTED = 3
    ABNORMAL = 4


# --- Settings (Config) with more than two options ---------------------------------


class CarpetStrategy(_NamedIntEnum):
    """Config.carpetCleanOption: what the robot does on carpets."""

    UNSPECIFIED = 0
    CROSS = 1  # lift the mop and drive across without cleaning
    BOOST = 2  # clean with more suction
    IGNORE = 3  # treat like any other floor
    AVOID = 4


class MopDrying(_NamedIntEnum):
    """Config.dryMopStrength."""

    UNSPECIFIED = 0
    QUIET = 1
    STRONG = 2
    SMART = 3  # strong, but quiet during do-not-disturb


class MopWashFrequency(_NamedIntEnum):
    """Config.cleanMopFreq: how often the mop is washed during a clean."""

    UNSPECIFIED = 0
    EFFICIENT = 1
    NORMAL = 2
    DEEP = 3


class CornerCleaning(_NamedIntEnum):
    """Config.cornerCleanMode."""

    UNSPECIFIED = 0
    FLEXIBLE_MOP = 1  # the extending mop reaches into corners
    TURN_ROBOT = 2  # the robot turns in corners
    OFF = 3


class ObstacleAvoidance(_NamedIntEnum):
    """Config.avoidMode."""

    UNSPECIFIED = 0
    SMART = 1
    CAREFUL = 2  # keeps more distance
    OFF = 3
