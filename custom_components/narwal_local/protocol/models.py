"""Decoded robot status, device and maintenance messages.

Field numbers come from app_protol (Narwal app 2.9.90) and were verified
against a real robot; see tests/fixtures for the captured payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .enums import (
    MAINTAIN_ITEM_NAMES,
    REPLACE_ITEM_NAMES,
    BagState,
    ChargingStatus,
    CleanWaterTankState,
    DetergentState,
    DustBoxState,
    FanLevel,
    FirmwareStatus,
    IdleStatus,
    MopHumidity,
    ServiceResult,
    SewageTankState,
    TaskType,
)
from .features import FEATURE_IS_BOOL, FEATURE_NAMES
from .pb import WIRE_FIXED32, WIRE_VARINT, parse, parse_packed_varints


def decode_result(payload: bytes) -> ServiceResult | int:
    """Read field 1 (the common result enum) of a command response."""
    for f in parse(payload):
        if f.num == 1 and f.wtype == WIRE_VARINT:
            return ServiceResult.from_value(f.int)
    return ServiceResult.UNSPECIFIED


@dataclass(slots=True)
class RobotBaseStatus:
    """RobotBaseStatus, from GetDeviceBaseStatus or a robot_base_status push.

    Only commonly useful fields are named. raw_fields keeps every scalar by
    field number, and robot_task_status keeps the nested task message (field 3)
    as {field: value} until its enums are verified on a robot.
    """

    result: ServiceResult | int = ServiceResult.UNSPECIFIED
    battery: float = 0.0  # 2
    error_codes: list[int] = field(default_factory=list)  # 1
    robot_task_status: dict[int, int] = field(default_factory=dict)  # 3
    binded_uuid: str = ""  # 13
    fan_level: FanLevel | int = FanLevel.UNSPECIFIED  # 26
    mop_humidity: MopHumidity | int = MopHumidity.UNSPECIFIED  # 29
    map_id: int = 0  # 30
    has_station: bool = False  # 44
    is_robot_at_origin: bool = False  # 45
    charging_status: ChargingStatus | int = ChargingStatus.UNSPECIFIED  # 47
    battery_cooling: int = 0  # 49
    raw_fields: dict[int, int] = field(default_factory=dict)

    def has_field(self, num: int) -> bool:
        """Whether the robot reported this RobotBaseStatus field (models
        without a station part or dust bag leave some out)."""
        return num in self.raw_fields

    def _enum_field(self, num: int, enum):
        return enum.from_value(self.raw_fields.get(num, 0))

    @property
    def clean_water(self) -> CleanWaterTankState | int:
        return self._enum_field(23, CleanWaterTankState)

    @property
    def dirty_water(self) -> SewageTankState | int:
        return self._enum_field(24, SewageTankState)

    @property
    def detergent(self) -> DetergentState | int:
        return self._enum_field(12, DetergentState)

    @property
    def dust_box(self) -> DustBoxState | int:
        return self._enum_field(20, DustBoxState)

    @property
    def dust_bag(self) -> BagState | int:
        return self._enum_field(21, BagState)

    @property
    def station_bag(self) -> BagState | int:
        return self._enum_field(39, BagState)

    @property
    def task(self) -> TaskType | int:
        return TaskType.from_value(self.robot_task_status.get(1, 0))

    @property
    def paused(self) -> bool:
        return bool(self.robot_task_status.get(2, 0))

    @property
    def idle_status(self) -> IdleStatus | int:
        return IdleStatus.from_value(self.robot_task_status.get(3, 0))

    @property
    def activity(self) -> Activity:
        return robot_activity(self)

    @property
    def in_clean_task(self) -> bool:
        """A cleaning job is running (whatever its current phase)."""
        return self.task in _CLEANING_TASKS


class Activity(StrEnum):
    """What the robot is doing, in Home Assistant's vacuum terms."""

    CLEANING = "cleaning"
    DOCKED = "docked"
    IDLE = "idle"
    PAUSED = "paused"
    RETURNING = "returning"
    ERROR = "error"


# Tasks that move the robot around the floor.
_CLEANING_TASKS = frozenset({
    TaskType.SWEEP, TaskType.MOP, TaskType.SWEEP_THEN_MOP, TaskType.SWEEP_AND_MOP,
    TaskType.SMART_CLEAN, TaskType.BUILD_MAP, TaskType.UPDATE_MAP,
    TaskType.COMPOSITE_CLEAN, TaskType.MAINTAIN_FLOOR, TaskType.DEPARTURE,
    TaskType.RELOCALIZATION, TaskType.TELECONTROL, TaskType.SEARCH_PERSON,
    TaskType.VIDEO_CRUISE, TaskType.SEARCH_PET,
})  # fmt: skip

# Station work with the robot docked.
_STATION_TASKS = frozenset({
    TaskType.WASH_AND_DRY_MOP, TaskType.DUST_GATHERING, TaskType.DRY_STATION_BAG,
})  # fmt: skip

# Per-task sub-status field -> values meaning "driving back to the station"
# (RECALL, AUTO_RECALL_TO_WASH, MANUAL_RECALL_TO_WASH) and "in the station
# mid-clean" (AUTO_WASH, MANUAL_WASH, CHARGING, DUST_GATHERING). The sweep enum
# has no wash steps. Verified on a sweep-and-mop clean (field 6): 16 and 4 in
# the station, 11 departure, 7 cleaning, 2 returning to wash.
_RETURNING_SUB = {4: {1}, 5: {1, 2, 3}, 6: {1, 2, 3}, 7: {1, 2, 3}, 8: {1, 2, 3}, 17: {1, 2, 3}}
_DOCKED_SUB = {
    4: {2, 12},  # sweep: CHARGING, DUST_GATHERING
    5: {4, 5, 6, 16},  # mop
    6: {4, 5, 6, 16},  # sweep and mop
    7: {4, 5, 6, 18},  # sweep then mop
    8: {4, 5, 6, 20},  # smart clean
    17: {4, 5, 6, 19},  # composite clean
}


def robot_activity(st: RobotBaseStatus) -> Activity:
    """Map RobotTaskStatus to an Activity.

    Derived from the app's enum names and checked against a full sweep-and-mop
    clean on a real robot (start in the station, cleaning, pause, return to
    wash, washing, drying). Charging means the robot sits on the dock's
    contacts, which overrides a moving state: the robot briefly reports
    ROOM_CLEAN or RETURNING while it is already charging.
    """
    if st.error_codes:
        return Activity.ERROR
    if st.paused:
        return Activity.PAUSED
    moving = _moving_activity(st)
    if moving is not None and st.charging_status is ChargingStatus.CHARGING:
        return Activity.DOCKED
    if moving is not None:
        return moving
    task = st.task
    if task in _STATION_TASKS:
        return Activity.DOCKED
    if task == TaskType.IDLE and st.idle_status in (
        IdleStatus.IN_STATION,
        IdleStatus.LOW_POWER_IN_STATION,
    ):
        return Activity.DOCKED
    if st.charging_status in (ChargingStatus.CHARGING, ChargingStatus.FULL):
        return Activity.DOCKED
    return Activity.IDLE


def _moving_activity(st: RobotBaseStatus) -> Activity | None:
    """CLEANING, RETURNING or DOCKED for clean and recall tasks, else None."""
    task, sub = st.task, st.robot_task_status
    if task in (TaskType.RECALL, TaskType.PARKING):
        return Activity.RETURNING
    if task in _CLEANING_TASKS:
        for fnum, values in _RETURNING_SUB.items():
            if sub.get(fnum) in values:
                return Activity.RETURNING
        for fnum, values in _DOCKED_SUB.items():
            if sub.get(fnum) in values:
                return Activity.DOCKED
        return Activity.CLEANING
    return None


def _decode_robot_base_status(buf: bytes, out: RobotBaseStatus) -> None:
    for f in parse(buf):
        if f.wtype == WIRE_VARINT:
            out.raw_fields[f.num] = f.int
        elif f.wtype == WIRE_FIXED32:
            out.raw_fields[f.num] = int.from_bytes(f.data, "little")
        match f.num:
            case 1:
                if f.wtype == WIRE_VARINT:
                    out.error_codes.append(f.int)
                else:
                    out.error_codes.extend(parse_packed_varints(f.data))
            case 2 if f.wtype == WIRE_FIXED32:
                out.battery = f.float
            case 3:
                out.robot_task_status = {
                    g.num: g.int for g in parse(f.data) if g.wtype == WIRE_VARINT
                }
            case 13:
                out.binded_uuid = f.text
            case 26:
                out.fan_level = FanLevel.from_value(f.int)
            case 29:
                out.mop_humidity = MopHumidity.from_value(f.int)
            case 30:
                out.map_id = f.int
            case 44:
                out.has_station = bool(f.int)
            case 45:
                out.is_robot_at_origin = bool(f.int)
            case 47:
                out.charging_status = ChargingStatus.from_value(f.int)
            case 49:
                out.battery_cooling = f.int


def decode_device_base_status(payload: bytes) -> RobotBaseStatus:
    """GetDeviceBaseStatus_Response{1 result, 2 RobotBaseStatus}."""
    out = RobotBaseStatus()
    for f in parse(payload):
        if f.num == 1:
            out.result = ServiceResult.from_value(f.int)
        elif f.num == 2:
            _decode_robot_base_status(f.data, out)
    return out


def decode_robot_base_status(payload: bytes) -> RobotBaseStatus:
    """A bare RobotBaseStatus, as pushed on /status/robot_base_status."""
    out = RobotBaseStatus()
    _decode_robot_base_status(payload, out)
    return out


@dataclass(slots=True)
class WorkingStatus:
    """msg/status/WorkingStatus push (progress of a running task)."""

    working_progress: float = 0.0  # 1, percent
    covered_area: float = 0.0  # 2, m²
    time_consuming: int = 0  # 3, seconds
    remained_time: int = 0  # 4, seconds
    cleaning_zone_id: int = 0  # 6, room id being cleaned


def decode_working_status(payload: bytes) -> WorkingStatus:
    ws = WorkingStatus()
    for f in parse(payload):
        match f.num:
            case 1 if f.wtype == WIRE_FIXED32:
                ws.working_progress = f.float
            case 2 if f.wtype == WIRE_FIXED32:
                ws.covered_area = f.float
            case 3:
                ws.time_consuming = f.int
            case 4:
                ws.remained_time = f.int
            case 6:
                ws.cleaning_zone_id = f.int
    return ws


@dataclass(slots=True)
class DeviceInfo:
    """/common/get_device_info. No named proto exists; fields were identified
    from the wire: 1 token, 2 device id (32 hex), 3 firmware version."""

    token: str = ""
    device_id: str = ""
    firmware_version: str = ""


def decode_device_info(payload: bytes) -> DeviceInfo:
    di = DeviceInfo()
    for f in parse(payload):
        if f.num == 1:
            di.token = f.text
        elif f.num == 2:
            di.device_id = f.text
        elif f.num == 3:
            di.firmware_version = f.text.strip()  # the robot appends a newline
    return di


@dataclass(slots=True)
class FeatureList:
    """/common/get_feature_list: bool support flags plus a few enum/counters."""

    flags: dict[str, bool] = field(default_factory=dict)
    other: dict[str, int] = field(default_factory=dict)

    @property
    def enabled(self) -> list[str]:
        return sorted(name for name, on in self.flags.items() if on)

    def supports(self, name: str) -> bool:
        return self.flags.get(name, False)


def decode_feature_list(payload: bytes) -> FeatureList:
    fl = FeatureList()
    for f in parse(payload):
        name = FEATURE_NAMES.get(f.num)
        if name is None:
            continue
        if f.num in FEATURE_IS_BOOL:
            fl.flags[name] = bool(f.value) if f.wtype == WIRE_VARINT else False
        elif f.wtype == WIRE_VARINT:
            fl.other[name] = f.int
    return fl


@dataclass(slots=True)
class ConsumableInfo:
    """/consumable/get_consumable_info: items that need maintenance or
    replacement now (not remaining lifetimes)."""

    maintain_items: list[str] = field(default_factory=list)
    replace_items: list[str] = field(default_factory=list)
    unified_error_code: int = 0


def _enum_names(buf: bytes, names: dict[int, str]) -> list[str]:
    return [names.get(v, str(v)) for v in parse_packed_varints(buf)]


def decode_consumable_info(payload: bytes) -> ConsumableInfo:
    ci = ConsumableInfo()
    for f in parse(payload):
        if f.num == 1:
            for g in parse(f.data):
                if g.num == 1:
                    ci.maintain_items = _enum_names(g.data, MAINTAIN_ITEM_NAMES)
                elif g.num == 2:
                    ci.replace_items = _enum_names(g.data, REPLACE_ITEM_NAMES)
        elif f.num == 2:
            ci.unified_error_code = f.int
    return ci


@dataclass(slots=True, frozen=True)
class FirmwareModule:
    """FirmwareVersionEntityMSG{1 firmwareId, 2 version, 3 versionText}."""

    group: str  # robot / station / vision
    slot: str  # mcu, cpu, ble, …
    firmware_id: str
    version: int
    version_text: str


@dataclass(slots=True)
class FirmwareVersion:
    """GetFirmwareVersion_Response{1 firmwareVersion, 2 firmwareVersionText,
    3 robot, 4 station, 5 vision, 6 unifiedErrorCode}."""

    version: int = 0
    version_text: str = ""
    modules: list[FirmwareModule] = field(default_factory=list)
    unified_error_code: int = 0


# Slot names per group message (FirmwareGroupMSG / FirmwareStationMSG / FirmwareVisionMSG).
_FIRMWARE_SLOTS: dict[str, dict[int, str]] = {
    "robot": {1: "mcu", 2: "ble", 3: "cpu", 4: "media", 5: "sensor"},
    "station": {1: "mcu", 2: "ble", 3: "cpu", 4: "media", 5: "media_b"},
    "vision": {1: "ai", 2: "cpu"},
}


def _decode_firmware_entity(group: str, slot: str, buf: bytes) -> FirmwareModule | None:
    fid, ver, text = "", 0, ""
    for f in parse(buf):
        if f.num == 1:
            fid = f.text
        elif f.num == 2:
            ver = f.int
        elif f.num == 3:
            text = f.text
    if not (fid or ver or text):
        return None  # the robot sends empty placeholders for absent chips
    return FirmwareModule(group, slot, fid, ver, text)


def decode_firmware_version(payload: bytes) -> FirmwareVersion:
    fv = FirmwareVersion()
    groups = {3: "robot", 4: "station", 5: "vision"}
    for f in parse(payload):
        if f.num == 1:
            fv.version = f.int
        elif f.num == 2:
            fv.version_text = f.text.strip()
        elif f.num in groups:
            group = groups[f.num]
            for g in parse(f.data):
                slot = _FIRMWARE_SLOTS[group].get(g.num, str(g.num))
                if module := _decode_firmware_entity(group, slot, g.data):
                    fv.modules.append(module)
        elif f.num == 6:
            fv.unified_error_code = f.int
    return fv


def decode_check_firmware(payload: bytes) -> FirmwareStatus | int:
    """CheckFirmware_Response{1 firmwareStatus}."""
    for f in parse(payload):
        if f.num == 1:
            return FirmwareStatus.from_value(f.int)
    return FirmwareStatus.UNSPECIFIED


@dataclass(slots=True, frozen=True)
class CleanReport:
    """/report/clean_report, pushed once when a clean has finished.

    Fields verified on a real robot: 1 progress (%), 2 area (m², float),
    3 duration (s), 6 start and 7 end (unix seconds). The report also carries
    per-room details and the cleaning track, which are not decoded here.
    """

    progress: int = 0
    area: float = 0.0
    duration: int = 0
    start: int = 0
    end: int = 0


def decode_clean_report(payload: bytes) -> CleanReport:
    values: dict[str, float | int] = {}
    for f in parse(payload):
        match f.num:
            case 1 if f.wtype == WIRE_VARINT:
                values["progress"] = f.int
            case 2 if f.wtype == WIRE_FIXED32:
                values["area"] = f.float
            case 3 if f.wtype == WIRE_VARINT:
                values["duration"] = f.int
            case 6 if f.wtype == WIRE_VARINT:
                values["start"] = f.int
            case 7 if f.wtype == WIRE_VARINT:
                values["end"] = f.int
    return CleanReport(**values)
