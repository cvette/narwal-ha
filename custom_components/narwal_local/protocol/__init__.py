"""Narwal robot local protocol (protobuf over ws://<ip>:9002).

Reconstructed from the Narwal app 2.9.90 and verified against a real robot.
Independent of Home Assistant so it can move to its own package later.
"""

from .client import (
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
from .map import MapInfo, Room, decode_get_map_response
from .models import (
    Activity,
    ConsumableInfo,
    DeviceInfo,
    FeatureList,
    FirmwareVersion,
    RobotBaseStatus,
    WorkingStatus,
    decode_robot_base_status,
    decode_working_status,
)
from .render import render_png

__all__ = [
    "TOPIC_DISPLAY_MAP",
    "TOPIC_ROBOT_BASE_STATUS",
    "TOPIC_WORKING_STATUS",
    "Activity",
    "ChargingStatus",
    "ConsumableInfo",
    "DeviceInfo",
    "FanLevel",
    "FeatureList",
    "FirmwareStatus",
    "FirmwareVersion",
    "ForbiddenType",
    "IdleStatus",
    "MapInfo",
    "Message",
    "MopHumidity",
    "NarwalClient",
    "NarwalCommandError",
    "NarwalConnectionError",
    "NarwalError",
    "NarwalRobot",
    "NarwalTimeoutError",
    "RobotBaseStatus",
    "Room",
    "ServiceResult",
    "TaskType",
    "WorkingStatus",
    "decode_get_map_response",
    "decode_robot_base_status",
    "decode_working_status",
    "render_png",
]
