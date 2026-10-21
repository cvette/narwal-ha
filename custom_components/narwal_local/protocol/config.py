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
from enum import StrEnum

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


# Setting -> (Config field, SetConfig_Request field)
FIELDS: dict[Setting, tuple[int, int]] = {
    Setting.VOLUME: (1, 1),  # volumePercentage
    Setting.DO_NOT_DISTURB: (4, 5),  # disturbMode
    Setting.AUTO_ADD_DETERGENT: (6, 7),  # autoAddDetergentEnabled
    Setting.CHILD_LOCK: (7, 8),  # childLockEnabled
    Setting.DUST_GATHERING: (27, 27),  # dustGatheringEnabled
    Setting.QUIET_DUST_GATHERING: (30, 30),  # quietDustGatheringEnabled
    Setting.DRY_DUST_BAG: (31, 31),  # dryRobotBagEnabled
    Setting.HOT_WATER_WASH: (32, 32),  # hotWaterWashEnabled
}

BOOL_SETTINGS: tuple[Setting, ...] = tuple(
    s for s in Setting if s not in (Setting.VOLUME, Setting.DO_NOT_DISTURB)
)


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
    """The decoded Config message. Proto3 leaves out false/zero values, so a
    missing flag reads as off."""

    volume: int = 0
    do_not_disturb: DisturbMode = field(default_factory=DisturbMode)
    flags: dict[Setting, bool] = field(default_factory=dict)
    raw_fields: dict[int, int] = field(default_factory=dict)

    def value(self, setting: Setting) -> int | bool | DisturbMode:
        if setting is Setting.VOLUME:
            return self.volume
        if setting is Setting.DO_NOT_DISTURB:
            return self.do_not_disturb
        return self.flags.get(setting, False)


def decode_config(payload: bytes) -> RobotConfig:
    """Decode a GetConfig_Response (or a bare Config message)."""
    fields = parse(payload)
    body = next((f.value for f in fields if f.num == 2 and f.wtype == WIRE_LEN), None)
    config = RobotConfig()
    if body is None:
        return config
    get_field = {get: s for s, (get, _) in FIELDS.items()}
    for f in parse(body):
        if f.wtype == WIRE_VARINT:
            config.raw_fields[f.num] = f.int
        setting = get_field.get(f.num)
        if setting is Setting.VOLUME and f.wtype == WIRE_VARINT:
            config.volume = f.int
        elif setting is Setting.DO_NOT_DISTURB and f.wtype == WIRE_LEN:
            config.do_not_disturb = DisturbMode.decode(f.value)
        elif setting is not None and f.wtype == WIRE_VARINT:
            config.flags[setting] = bool(f.int)
    for setting in BOOL_SETTINGS:
        config.flags.setdefault(setting, False)
    return config


def build_set_config_request(setting: Setting, value: int | bool | DisturbMode) -> bytes:
    """One SetConfig_Request. A oneof member is written even when it holds
    the default (false / 0), which is how the robot tells "set to off" from
    "nothing set"."""
    num = FIELDS[setting][1]
    w = Writer()
    if setting is Setting.DO_NOT_DISTURB:
        if not isinstance(value, DisturbMode):
            raise TypeError("do_not_disturb takes a DisturbMode")
        w.bytes_(num, value.encode())
    elif setting is Setting.VOLUME:
        if not 0 <= int(value) <= 100:
            raise ValueError("volume is a percentage")
        w.varint(num, int(value), force=True)
    else:
        w.varint(num, 1 if value else 0, force=True)
    return bytes(w)
