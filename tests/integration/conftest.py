"""Home Assistant test fixtures: a fake robot fed from the real fixtures.

Skipped when Home Assistant is not installed (the protocol tests run without it).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import CONF_HOST, CONF_PORT  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.narwal_local.const import DOMAIN  # noqa: E402
from custom_components.narwal_local.protocol import (  # noqa: E402
    Message,
    NarwalCommandError,
    NarwalConnectionError,
    ServiceResult,
)
from custom_components.narwal_local.protocol.frame import Header  # noqa: E402
from custom_components.narwal_local.protocol.map import decode_get_map_response  # noqa: E402
from custom_components.narwal_local.protocol.models import (  # noqa: E402
    decode_consumable_info,
    decode_device_base_status,
    decode_device_info,
    decode_feature_list,
    decode_firmware_version,
)
from custom_components.narwal_local.protocol.pb import Writer  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load_bin(name: str) -> bytes:
    return (FIXTURES / f"{name}.bin").read_bytes()


DEVICE_ID = "0123456789abcdef0123456789abcdef"  # redacted id in the fixtures
HOST = "192.168.1.113"


class FakeRobot:
    """Stands in for NarwalRobot; answers from captured payloads."""

    def __init__(self) -> None:
        self.host = HOST
        self.port = 9002
        self.connected = False
        self.fail_connect = False
        self.fail_command: ServiceResult | None = None
        self.calls: list[tuple] = []
        self.push_callbacks: list[Callable[[Message], None]] = []
        self.disconnect_callbacks: list[Callable[[], None]] = []
        self.status = decode_device_base_status(load_bin("device_base_status"))
        self.device = decode_device_info(load_bin("device_info"))
        self.features = decode_feature_list(load_bin("feature_list"))
        self.firmware = decode_firmware_version(load_bin("firmware_version"))
        self.consumables = decode_consumable_info(load_bin("consumable_info"))
        self.map = decode_get_map_response(load_bin("get_map"))
        self.map_fetches = 0

    def __call__(self, host: str, port: int = 9002, **_: object) -> FakeRobot:
        """Acts as the NarwalRobot constructor."""
        self.host, self.port = host, port
        return self

    async def connect(self) -> None:
        if self.fail_connect:
            raise NarwalConnectionError("unreachable")
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    def add_push_callback(self, cb):
        self.push_callbacks.append(cb)
        return lambda: self.push_callbacks.remove(cb)

    def add_disconnect_callback(self, cb):
        self.disconnect_callbacks.append(cb)
        return lambda: self.disconnect_callbacks.remove(cb)

    def _ensure(self) -> None:
        if not self.connected:
            raise NarwalConnectionError("not connected")

    async def get_status(self):
        self._ensure()
        return replace(self.status, robot_task_status=dict(self.status.robot_task_status))

    async def get_device_info(self):
        self._ensure()
        return self.device

    async def get_features(self):
        self._ensure()
        return self.features

    async def get_firmware_version(self):
        self._ensure()
        return self.firmware

    async def get_consumables(self):
        self._ensure()
        return self.consumables

    async def get_map(self):
        self._ensure()
        self.map_fetches += 1
        return self.map

    async def activate_reporting(self, seconds: int = 60):
        self._ensure()
        self.calls.append(("activate_reporting", seconds))
        return ServiceResult.PERFORM_SUCCESS

    async def _command(self, *call) -> None:
        self._ensure()
        self.calls.append(call)
        if self.fail_command is not None:
            raise NarwalCommandError(f"/{call[0]}", self.fail_command)

    async def dock(self):
        await self._command("dock")

    async def pause(self, *ids):
        await self._command("pause", *ids)

    async def resume(self, *ids):
        await self._command("resume", *ids)

    async def set_fan_level(self, level):
        await self._command("set_fan_level", level)

    async def set_mop_humidity(self, humidity):
        await self._command("set_mop_humidity", humidity)

    async def start_clean(self, rooms=None, *, mode=None, **_):
        await self._command("start_clean", list(rooms) if rooms else None, mode)

    async def stop(self):
        await self._command("stop")

    async def locate(self):
        await self._command("locate")

    # --- test helpers ---------------------------------------------------

    def push(self, topic: str, payload: bytes) -> None:
        header = Header(url=f"/pid0000000/{DEVICE_ID}{topic}", uuid="push")
        for cb in list(self.push_callbacks):
            cb(Message(header, payload))

    def drop(self) -> None:
        self.connected = False
        for cb in list(self.disconnect_callbacks):
            cb()


def status_payload(
    task: dict[int, int],
    *,
    battery: float = 80.0,
    fan: int = 3,
    mop: int = 2,
    charging: int = 2,
    errors: tuple[int, ...] = (),
    extra: dict[int, int] | None = None,
) -> bytes:
    """A RobotBaseStatus push body; `extra` adds varint fields (station states)."""
    w = Writer()
    for e in errors:
        w.varint(1, e, force=True)
    w.float_(2, battery)
    tw = Writer()
    for num, value in task.items():
        tw.varint(num, int(value), force=True)
    w.message(3, tw)
    w.varint(26, fan).varint(29, mop).varint(30, 1).varint(44, 1).varint(47, charging)
    for num, value in (extra or {}).items():
        w.varint(num, value, force=True)
    return bytes(w)


# The synthetic map's border frame: display cell (col, row) = (x + 40, y + 30).
def display_map_payload(col: float, row: float, theta: float = 0.0) -> bytes:
    """A /map/display_map push with the robot at a display cell."""
    point = Writer().float_(1, col - 40).float_(2, row - 30)
    return bytes(Writer().message(1, Writer().message(1, point).float_(2, theta)).varint(10, 1))


def clean_report_payload(area: float, seconds: int, start: int, end: int) -> bytes:
    return bytes(
        Writer().varint(1, 100).float_(2, area).varint(3, seconds).varint(6, start).varint(7, end)
    )


def working_payload(progress: float, area: float, seconds: int, remain: int, zone: int) -> bytes:
    return bytes(
        Writer().float_(1, progress).float_(2, area).varint(3, seconds).varint(4, remain).varint(6, zone)
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def robot() -> FakeRobot:
    fake = FakeRobot()
    with (
        patch("custom_components.narwal_local.NarwalRobot", fake),
        patch("custom_components.narwal_local.config_flow.NarwalRobot", fake),
    ):
        yield fake


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Narwal",
        unique_id=DEVICE_ID,
        data={CONF_HOST: HOST, CONF_PORT: 9002},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
