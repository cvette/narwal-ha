"""Read-only checks against a real robot. Skipped unless NARWAL_HOST is set:

    NARWAL_HOST=192.168.1.113 pytest -m live
"""

from __future__ import annotations

import os

import pytest

from protocol.client import NarwalRobot
from protocol.enums import ServiceResult

HOST = os.environ.get("NARWAL_HOST")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not HOST, reason="set NARWAL_HOST to run against a robot"),
]


async def test_live_read_only() -> None:
    async with NarwalRobot(HOST) as robot:
        st = await robot.get_status()
        assert st.result is ServiceResult.PERFORM_SUCCESS
        assert 0 <= st.battery <= 100
        info = await robot.get_device_info()
        assert info.firmware_version.startswith("v")
        fv = await robot.get_firmware_version()
        assert fv.modules
        assert (await robot.get_features()).enabled
        await robot.get_consumables()
        mi = await robot.get_map()
        assert mi.robot_has_map and mi.rooms and len(mi.room_grid()) == mi.width * mi.height
