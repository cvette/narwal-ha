"""Robot settings: /config/get and /config/set.

GetConfig_Response is {1 result, 2 Config, 3 unifiedErrorCode}. SetConfig's
request is a oneof that carries exactly one setting per call, and its field
numbers differ from Config's (from field 4 on, Set skips 4 and shifts by one,
skips cleanCorner, buildDateTime and wakeVoiceWords). Both tables come from
app_protol (Narwal app 2.9.90); values written are verified by reading back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum, StrEnum, auto

from .enums import CarpetStrategy, CornerCleaning, MopDrying, MopWashFrequency, ObstacleAvoidance
from .pb import WIRE_LEN, WIRE_VARINT, Writer, parse

URL_GET_CONFIG = "/config/get"
URL_SET_CONFIG = "/config/set"


class Setting(StrEnum):
    """Settings this library reads and writes."""

    VOLUME = "volume"
    DO_NOT_DISTURB = "do_not_disturb"
    AUTO_ADD_DETERGENT = "auto_add_detergent"
    CHILD_LOCK = "child_lock"
    DUST_GATHERING = "dust_gathering"
    QUIET_DUST_GATHERING = "quiet_dust_gathering"
    DRY_DUST_BAG = "dry_dust_bag"
    HOT_WATER_WASH = "hot_water_wash"
    HEAVY_DIRT_DEEP_CLEAN = "heavy_dirt_deep_clean"
    PET_MODE = "pet_mode"
    CARPET_FIRST = "carpet_first"
    CARPET_DEEP_CLEAN = "carpet_deep_clean"
    STATION_LIGHT = "station_light"
    CARPET_STRATEGY = "carpet_strategy"
    MOP_DRYING = "mop_drying"
    MOP_WASH_FREQUENCY = "mop_wash_frequency"
    CORNER_CLEANING = "corner_cleaning"
    OBSTACLE_AVOIDANCE = "obstacle_avoidance"


class Kind(Enum):
    """How a setting is encoded."""

    NUMBER = auto()  # plain int (volume)
    DISTURB_MODE = auto()  # DisturbMode message
    BOOL = auto()  # bool; left out of Config when off
    TOGGLE = auto()  # two-value enum, 1 = off and 2 = on (…_DISABLE/…_ENABLE, LED_OFF/LED_ON)
    ENUM = auto()  # enum with more options; 0 (unspecified) means not reported


@dataclass(frozen=True, slots=True)
class SettingInfo:
    get_field: int  # in Config
    set_field: int  # in SetConfig_Request
    kind: Kind
    enum: type[Enum] | None = None


SETTINGS: dict[Setting, SettingInfo] = {
    Setting.VOLUME: SettingInfo(1, 1, Kind.NUMBER),  # volumePercentage
    Setting.DO_NOT_DISTURB: SettingInfo(4, 5, Kind.DISTURB_MODE),  # disturbMode
    Setting.AUTO_ADD_DETERGENT: SettingInfo(6, 7, Kind.BOOL),  # autoAddDetergentEnabled
    Setting.CHILD_LOCK: SettingInfo(7, 8, Kind.BOOL),  # childLockEnabled
    Setting.MOP_DRYING: SettingInfo(12, 13, Kind.ENUM, MopDrying),  # dryMopStrength
    Setting.MOP_WASH_FREQUENCY: SettingInfo(13, 14, Kind.ENUM, MopWashFrequency),  # cleanMopFreq
    Setting.CARPET_STRATEGY: SettingInfo(15, 15, Kind.ENUM, CarpetStrategy),  # carpetCleanOption
    Setting.PET_MODE: SettingInfo(22, 22, Kind.BOOL),  # petMode
    Setting.DUST_GATHERING: SettingInfo(27, 27, Kind.BOOL),  # dustGatheringEnabled
    Setting.QUIET_DUST_GATHERING: SettingInfo(30, 30, Kind.BOOL),  # quietDustGatheringEnabled
    Setting.DRY_DUST_BAG: SettingInfo(31, 31, Kind.BOOL),  # dryRobotBagEnabled
    Setting.HOT_WATER_WASH: SettingInfo(32, 32, Kind.BOOL),  # hotWaterWashEnabled
    Setting.HEAVY_DIRT_DEEP_CLEAN: SettingInfo(33, 33, Kind.BOOL),  # massiveDirtyDeepCleanEnable
    Setting.OBSTACLE_AVOIDANCE: SettingInfo(34, 34, Kind.ENUM, ObstacleAvoidance),  # avoidMode
    Setting.CORNER_CLEANING: SettingInfo(41, 41, Kind.ENUM, CornerCleaning),  # cornerCleanMode
    Setting.CARPET_FIRST: SettingInfo(46, 45, Kind.TOGGLE),  # carpetCleanPriorityOption
    Setting.CARPET_DEEP_CLEAN: SettingInfo(47, 46, Kind.TOGGLE),  # carpetDeepCleanOption
    Setting.STATION_LIGHT: SettingInfo(51, 49, Kind.TOGGLE),  # stationLightCtrlType
}

TOGGLE_OFF, TOGGLE_ON = 1, 2


def _seconds(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _time(seconds: int) -> time:
    seconds %= 86400
    return time(seconds // 3600, seconds // 60 % 60, seconds % 60)


@dataclass(frozen=True, slots=True)
class DisturbMode:
    """DisturbMode {1 enabled, 2 beginTime, 3 endTime}; times are seconds
    after local midnight (the robot keeps its own time zone)."""

    enabled: bool = False
    start: time = time(22, 0)
    end: time = time(8, 0)

    def encode(self) -> bytes:
        w = Writer().boolean(1, self.enabled)
        w.varint(2, _seconds(self.start)).varint(3, _seconds(self.end))
        return bytes(w)

    @classmethod
    def decode(cls, payload: bytes) -> DisturbMode:
        values = {f.num: f.int for f in parse(payload) if f.wtype == WIRE_VARINT}
        return cls(bool(values.get(1)), _time(values.get(2, 0)), _time(values.get(3, 0)))


@dataclass(slots=True)
class RobotConfig:
    """The decoded Config message.

    Proto3 leaves out false/zero values: a missing BOOL reads as off, while a
    TOGGLE or ENUM setting the robot does not send is not in `reported` (the
    robot does not have it).
    """

    volume: int = 0
    do_not_disturb: DisturbMode = field(default_factory=DisturbMode)
    flags: dict[Setting, bool] = field(default_factory=dict)  # BOOL and TOGGLE settings
    options: dict[Setting, Enum | int] = field(default_factory=dict)  # ENUM settings
    reported: set[Setting] = field(default_factory=set)
    raw_fields: dict[int, int] = field(default_factory=dict)

    def value(self, setting: Setting) -> int | bool | DisturbMode | Enum | None:
        if setting is Setting.VOLUME:
            return self.volume
        if setting is Setting.DO_NOT_DISTURB:
            return self.do_not_disturb
        if SETTINGS[setting].kind is Kind.ENUM:
            return self.options.get(setting)
        return self.flags.get(setting)

    def has(self, setting: Setting) -> bool:
        """Whether the robot has this setting (BOOLs always count)."""
        return SETTINGS[setting].kind is Kind.BOOL or setting in self.reported


def _from_value(enum: type[Enum], value: int) -> Enum | int:
    try:
        return enum(value)
    except ValueError:
        return value


def decode_config(payload: bytes) -> RobotConfig:
    """Decode a GetConfig_Response (or a bare Config message)."""
    fields = parse(payload)
    body = next((f.value for f in fields if f.num == 2 and f.wtype == WIRE_LEN), None)
    config = RobotConfig()
    if body is None:
        return config
    by_get_field = {info.get_field: s for s, info in SETTINGS.items()}
    for f in parse(body):
        if f.wtype == WIRE_VARINT:
            config.raw_fields[f.num] = f.int
        setting = by_get_field.get(f.num)
        if setting is None:
            continue
        kind = SETTINGS[setting].kind
        if kind is Kind.DISTURB_MODE:
            if f.wtype == WIRE_LEN:
                config.do_not_disturb = DisturbMode.decode(f.value)
                config.reported.add(setting)
            continue
        if f.wtype != WIRE_VARINT:
            continue
        config.reported.add(setting)
        if kind is Kind.NUMBER:
            config.volume = f.int
        elif kind is Kind.BOOL:
            config.flags[setting] = bool(f.int)
        elif kind is Kind.TOGGLE:
            config.flags[setting] = f.int == TOGGLE_ON
        else:
            config.options[setting] = _from_value(SETTINGS[setting].enum, f.int)
    for setting, info in SETTINGS.items():
        if info.kind is Kind.BOOL:
            config.flags.setdefault(setting, False)
    return config


def build_set_config_request(setting: Setting, value: int | bool | DisturbMode | Enum) -> bytes:
    """One SetConfig_Request. A oneof member is written even when it holds
    the default (false / 0), which is how the robot tells "set to off" from
    "nothing set"."""
    info = SETTINGS[setting]
    w = Writer()
    match info.kind:
        case Kind.DISTURB_MODE:
            if not isinstance(value, DisturbMode):
                raise TypeError("do_not_disturb takes a DisturbMode")
            w.bytes_(info.set_field, value.encode())
        case Kind.NUMBER:
            if not 0 <= int(value) <= 100:
                raise ValueError("volume is a percentage")
            w.varint(info.set_field, int(value), force=True)
        case Kind.BOOL:
            w.varint(info.set_field, 1 if value else 0, force=True)
        case Kind.TOGGLE:
            w.varint(info.set_field, TOGGLE_ON if value else TOGGLE_OFF, force=True)
        case Kind.ENUM:
            if int(value) <= 0:
                raise ValueError(f"{setting} needs one of its options, not {value!r}")
            w.varint(info.set_field, int(value), force=True)
    return bytes(w)
