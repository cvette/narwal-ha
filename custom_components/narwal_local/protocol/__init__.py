"""Narwal robot local protocol (protobuf over ws://<ip>:9002).

Reconstructed from the Narwal app 2.9.90 and verified against a real robot.
Independent of Home Assistant so it can move to its own package later.
"""

from .cleaning import CleanMode, CleanZoneType, build_clean_task_request, build_start_request
from .client import (
    TOPIC_CLEAN_REPORT,
    TOPIC_DISPLAY_MAP,
    TOPIC_ROBOT_BASE_STATUS,
    TOPIC_WORKING_STATUS,
    Message,
    NarwalClient,
    NarwalCommandError,
    NarwalConnectionError,
    NarwalError,
    NarwalRobot,
    NarwalTimeoutError,
)
from .enums import (
    ChargingStatus,
    FanLevel,
    FirmwareStatus,
    ForbiddenType,
    IdleStatus,
    MopHumidity,
    ServiceResult,
    TaskType,
)
from .map import DisplayMap, MapInfo, Pose, Room, decode_display_map, decode_get_map_response
from .models import (
    Activity,
    CleanReport,
    ConsumableInfo,
    DeviceInfo,
    FeatureList,
    FirmwareVersion,
    RobotBaseStatus,
    WorkingStatus,
    decode_clean_report,
    decode_robot_base_status,
    decode_working_status,
)
from .render import MapRenderer, add_labels, add_robot, add_room_labels, render_png

__all__ = [
    "TOPIC_CLEAN_REPORT",
    "TOPIC_DISPLAY_MAP",
    "TOPIC_ROBOT_BASE_STATUS",
    "TOPIC_WORKING_STATUS",
    "Activity",
    "ChargingStatus",
    "CleanMode",
    "CleanReport",
    "CleanZoneType",
    "ConsumableInfo",
    "DeviceInfo",
    "DisplayMap",
    "FanLevel",
    "FeatureList",
    "FirmwareStatus",
    "FirmwareVersion",
    "ForbiddenType",
    "IdleStatus",
    "MapInfo",
    "MapRenderer",
    "Message",
    "MopHumidity",
    "NarwalClient",
    "NarwalCommandError",
    "NarwalConnectionError",
    "NarwalError",
    "NarwalRobot",
    "NarwalTimeoutError",
    "Pose",
    "RobotBaseStatus",
    "Room",
    "ServiceResult",
    "TaskType",
    "WorkingStatus",
    "add_labels",
    "add_robot",
    "add_room_labels",
    "build_clean_task_request",
    "build_start_request",
    "decode_clean_report",
    "decode_display_map",
    "decode_get_map_response",
    "decode_robot_base_status",
    "decode_working_status",
    "render_png",
]
