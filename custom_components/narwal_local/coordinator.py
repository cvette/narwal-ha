"""Coordinator: one connection to the robot, push updates, polling fallback."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field, replace
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONSUMABLES_INTERVAL,
    DOMAIN,
    KEEPALIVE_INTERVAL,
    MAP_INTERVAL,
    POLL_INTERVAL,
    REPORT_SECONDS,
)
from .map_objects import ObjectNames
from .protocol import (
    TOPIC_ROBOT_BASE_STATUS,
    TOPIC_WORKING_STATUS,
    ConsumableInfo,
    DeviceInfo,
    FeatureList,
    FirmwareVersion,
    MapInfo,
    Message,
    NarwalCommandError,
    NarwalError,
    NarwalRobot,
    RobotBaseStatus,
    WorkingStatus,
    decode_robot_base_status,
    decode_working_status,
)

_LOGGER = logging.getLogger(__name__)

type NarwalConfigEntry = ConfigEntry[NarwalCoordinator]


@dataclass(frozen=True, slots=True)
class NarwalData:
    """Everything the entities read."""

    status: RobotBaseStatus
    working: WorkingStatus | None = None
    consumables: ConsumableInfo | None = None
    map: MapInfo | None = None
    names: ObjectNames = field(default_factory=ObjectNames)


@dataclass(frozen=True, slots=True)
class NarwalStatic:
    """Read once at setup."""

    device: DeviceInfo
    features: FeatureList
    firmware: FirmwareVersion | None


class NarwalCoordinator(DataUpdateCoordinator[NarwalData]):
    """Holds the robot connection and the latest state."""

    config_entry: NarwalConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: NarwalConfigEntry,
        robot: NarwalRobot,
        static: NarwalStatic,
        names: ObjectNames | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
        )
        self.robot = robot
        self.static = static
        self.names = names or ObjectNames()
        self._consumables_due = dt_util.utcnow()
        self._map_due = dt_util.utcnow()

    @property
    def device_id(self) -> str:
        return self.static.device.device_id

    async def _async_setup(self) -> None:
        """Subscribe to pushes and keep the robot reporting."""
        entry = self.config_entry
        entry.async_on_unload(self.robot.add_push_callback(self._handle_push))
        entry.async_on_unload(self.robot.add_disconnect_callback(self._handle_disconnect))
        entry.async_on_unload(
            async_track_time_interval(self.hass, self._async_keepalive, KEEPALIVE_INTERVAL)
        )

    async def _async_update_data(self) -> NarwalData:
        try:
            if not self.robot.connected:
                await self.robot.connect()
                await self.robot.activate_reporting(REPORT_SECONDS)
            status = await self.robot.get_status()
            previous = self.data
            consumables = previous.consumables if previous else None
            map_info = previous.map if previous else None
            now = dt_util.utcnow()
            if consumables is None or now >= self._consumables_due:
                consumables = await self.robot.get_consumables()
                self._consumables_due = now + CONSUMABLES_INTERVAL
            if map_info is None or now >= self._map_due or map_info.map_id != status.map_id:
                map_info = await self.robot.get_map()
                self._map_due = now + MAP_INTERVAL
        except NarwalError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        return NarwalData(
            status=status,
            working=previous.working if previous else None,
            consumables=consumables,
            map=map_info,
            names=self.names,
        )

    @callback
    def _handle_push(self, msg: Message) -> None:
        if self.data is None:
            return
        try:
            if msg.topic == TOPIC_ROBOT_BASE_STATUS:
                status = decode_robot_base_status(msg.payload)
                # The push carries no result field; keep the last one.
                status.result = self.data.status.result
                self.async_set_updated_data(replace(self.data, status=status))
            elif msg.topic == TOPIC_WORKING_STATUS:
                working = decode_working_status(msg.payload)
                self.async_set_updated_data(replace(self.data, working=working))
        except ValueError:
            _LOGGER.debug("Undecodable push on %s: %s", msg.topic, msg.payload.hex())

    @callback
    def _handle_disconnect(self) -> None:
        _LOGGER.debug("Connection to %s lost", self.robot.host)
        self.async_set_update_error(UpdateFailed("connection lost"))
        self.config_entry.async_create_background_task(
            self.hass, self.async_request_refresh(), "narwal_local reconnect"
        )

    async def _async_keepalive(self, _now: datetime) -> None:
        if not self.robot.connected:
            return
        try:
            await self.robot.activate_reporting(REPORT_SECONDS)
        except NarwalError as err:
            _LOGGER.debug("Keepalive failed: %s", err)

    async def async_command(self, command: Awaitable[object]) -> None:
        """Run a robot command, turning protocol errors into HA errors."""
        try:
            await command
        except NarwalCommandError as err:
            result = getattr(err.result, "name", str(err.result))
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"result": result},
            ) from err
        except NarwalError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.robot.close()
