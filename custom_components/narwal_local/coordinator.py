"""Coordinator: one connection to the robot, push updates, polling fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
import logging
import math

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
    TIMELINE_MAX,
    PATH_MAX_POINTS,
    PATH_MIN_STEP,
    POLL_INTERVAL,
    RECONNECT_DELAYS,
    REPORT_SECONDS,
)
from .map_objects import ObjectNames
from .protocol import (
    TOPIC_CLEAN_REPORT,
    TOPIC_TIME_LINE,
    BatteryInfo,
    TOPIC_DISPLAY_MAP,
    TOPIC_ROBOT_BASE_STATUS,
    TOPIC_WORKING_STATUS,
    CleanMode,
    CleanPlan,
    CleanReport,
    ContinueTask,
    ConsumableInfo,
    DeviceInfo,
    FeatureList,
    FirmwareVersion,
    Language,
    MapInfo,
    MapSummary,
    Message,
    NarwalCommandError,
    NarwalError,
    NarwalRobot,
    NarwalTimeoutError,
    NoGoZone,
    Pose,
    PrimaryTask,
    RobotBaseStatus,
    RobotConfig,
    TimelineEvent,
    Setting,
    WorkingStatus,
    decode_clean_report,
    decode_display_map,
    decode_robot_base_status,
    decode_timeline,
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
    last_report: CleanReport | None = None
    names: ObjectNames = field(default_factory=ObjectNames)
    config: RobotConfig | None = None
    plans: tuple[CleanPlan, ...] | None = None  # saved in the Narwal app
    maps: tuple[MapSummary, ...] | None = None  # all maps (floors)
    battery: BatteryInfo | None = None  # health, cycles, temperature, …
    continue_task: ContinueTask | None = None  # an interrupted clean to resume
    dry_mop_remain: int | None = None  # seconds of mop drying left
    timeline: tuple[TimelineEvent, ...] = ()  # events of the current / last task
    language: Language | int | None = None  # the voice language


@dataclass(frozen=True, slots=True)
class NarwalStatic:
    """Read once at setup."""

    device: DeviceInfo
    features: FeatureList
    firmware: FirmwareVersion | None
    languages: tuple[Language | int, ...] = ()  # voice languages the robot has


@dataclass(slots=True)
class LiveState:
    """Robot position from display_map pushes, about once a second while the
    robot is active. Kept outside NarwalData so a moving robot does not make
    every entity write its state each second; entities that care subscribe
    with NarwalCoordinator.async_add_live_listener."""

    robot: Pose | None = None
    path: list[tuple[float, float]] = field(default_factory=list)
    version: int = 0


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
        self.live = LiveState()
        # Mode for cleans started from Home Assistant; set by the clean mode
        # select (the robot keeps no "current mode" of its own).
        self.clean_mode = CleanMode.SWEEP_MOP
        self._live_listeners: list[Callable[[], None]] = []
        self._consumables_due = dt_util.utcnow()
        self._map_due = dt_util.utcnow()
        self._reconnecting = False

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
            plans = previous.plans if previous else None
            maps = previous.maps if previous else None
            language = previous.language if previous else None
            now = dt_util.utcnow()
            if consumables is None or now >= self._consumables_due:
                consumables = await self.robot.get_consumables()
                self._consumables_due = now + CONSUMABLES_INTERVAL
            if map_info is None or now >= self._map_due or map_info.map_id != status.map_id:
                map_info = await self.robot.get_map()
                plans = await self._async_get_plans(plans)
                maps = await self._async_get_maps(maps)
                language = await self._async_get_language(language)
                self._map_due = now + MAP_INTERVAL
            config = await self._async_get_config(previous.config if previous else None)
            battery = await self._async_get_battery(previous.battery if previous else None)
            continue_task, dry_mop_remain = await self._async_get_station_extras(status, previous)
            timeline = await self._async_get_timeline(previous.timeline if previous else ())
        except NarwalError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        self._track_clean_start(previous.status if previous else None, status)
        return NarwalData(
            status=status,
            working=previous.working if previous else None,
            consumables=consumables,
            map=map_info,
            last_report=previous.last_report if previous else None,
            names=self.names,
            config=config,
            plans=plans,
            maps=maps,
            battery=battery,
            continue_task=continue_task,
            dry_mop_remain=dry_mop_remain,
            timeline=timeline,
            language=language,
        )

    async def _async_get_timeline(self, previous: tuple[TimelineEvent, ...]) -> tuple[TimelineEvent, ...]:
        """The robot forgets its timeline (on a restart, for example); keep
        what we collected until it reports events again."""
        try:
            events = await self.robot.get_timeline()
        except (NarwalCommandError, NarwalTimeoutError) as err:
            _LOGGER.debug("Reading the timeline failed: %s", err)
            return previous
        return tuple(events[-TIMELINE_MAX:]) if events else previous

    async def _async_get_language(self, previous: Language | int | None) -> Language | int | None:
        if not self.static.languages:
            return None
        try:
            return await self.robot.get_language()
        except (NarwalCommandError, NarwalTimeoutError) as err:
            _LOGGER.debug("Reading the voice language failed: %s", err)
            return previous

    async def async_set_language(self, language: Language) -> None:
        await self.async_command(self.robot.set_language(language))
        self.async_set_updated_data(replace(self.data, language=language))

    async def _async_get_station_extras(
        self, status: RobotBaseStatus, previous: NarwalData | None
    ) -> tuple[ContinueTask | None, int | None]:
        """An interrupted clean to resume and the mop drying time left; robots
        without a station or these services keep what they had."""
        continue_task = previous.continue_task if previous else None
        dry = previous.dry_mop_remain if previous else None
        if not status.has_station:
            return continue_task, dry
        try:
            continue_task = await self.robot.get_continue_task()
            dry = await self.robot.get_dry_mop_remain_time()
        except (NarwalCommandError, NarwalTimeoutError) as err:
            _LOGGER.debug("Reading the station extras failed: %s", err)
        return continue_task, dry

    async def _async_get_maps(self, previous: tuple[MapSummary, ...] | None) -> tuple[MapSummary, ...] | None:
        """All maps, read with the map, for robots that keep several."""
        if not self.static.features.supports("supportMultiMap"):
            return None
        try:
            return tuple(m for m in await self.robot.get_maps() if not m.temporary)
        except (NarwalCommandError, NarwalTimeoutError) as err:
            _LOGGER.debug("Reading the maps failed: %s", err)
            return previous

    async def async_switch_map(self, map_id: int) -> None:
        """Switch to another map and read it right away."""
        await self.async_command(self.robot.switch_map(map_id))
        self._map_due = dt_util.utcnow()
        await self.async_request_refresh()

    async def _async_get_battery(self, previous: BatteryInfo | None) -> BatteryInfo | None:
        """Battery health, for robots that report it."""
        if not self.static.features.supports("supportBatteryHealthInfo"):
            return None
        try:
            return await self.robot.get_battery_info()
        except (NarwalCommandError, NarwalTimeoutError) as err:
            _LOGGER.debug("Reading the battery info failed: %s", err)
            return previous

    async def _async_get_plans(
        self, previous: tuple[CleanPlan, ...] | None
    ) -> tuple[CleanPlan, ...] | None:
        """Cleaning plans, read with the map; a robot without them keeps none."""
        try:
            return tuple(await self.robot.get_clean_plans())
        except (NarwalCommandError, NarwalTimeoutError) as err:
            _LOGGER.debug("Reading the cleaning plans failed: %s", err)
            return previous

    async def _async_get_config(self, previous: RobotConfig | None) -> RobotConfig | None:
        """The robot's settings; a robot that does not answer /config/get
        simply gets no settings entities."""
        try:
            return await self.robot.get_config()
        except (NarwalCommandError, NarwalTimeoutError) as err:
            _LOGGER.debug("Reading the settings failed: %s", err)
            return previous

    async def async_edit_no_go_zones(
        self, add: list[NoGoZone] | None = None, delete: list[int] | None = None
    ) -> None:
        """Change no-go zones and take the robot's map as it is afterwards."""
        map_info: MapInfo | None = None

        async def edit() -> None:
            nonlocal map_info
            map_info = await self.robot.edit_no_go_zones(add or (), delete or ())

        await self.async_command(edit())
        self._map_due = dt_util.utcnow() + MAP_INTERVAL
        self.async_set_updated_data(replace(self.data, map=map_info))

    async def async_refresh_consumables(self) -> None:
        """Re-read the due parts now, e.g. after a reset."""
        self._consumables_due = dt_util.utcnow()
        await self.async_request_refresh()

    async def async_set_config(self, setting: Setting, value: object) -> None:
        """Change a setting, then read the settings back so the entities show
        what the robot actually stored."""
        await self.async_command(self.robot.set_config(setting, value))
        try:
            config = await self.robot.get_config()
        except NarwalError as err:
            _LOGGER.debug("Reading back the settings failed: %s", err)
            return
        self.async_set_updated_data(replace(self.data, config=config))

    # --- pushes -----------------------------------------------------------

    @callback
    def _handle_push(self, msg: Message) -> None:
        if self.data is None:
            return
        try:
            if msg.topic == TOPIC_DISPLAY_MAP:
                self._handle_display_map(msg.payload)
            elif msg.topic == TOPIC_ROBOT_BASE_STATUS:
                status = decode_robot_base_status(msg.payload)
                # The push carries no result field; keep the last one.
                status.result = self.data.status.result
                self._track_clean_start(self.data.status, status)
                self.async_set_updated_data(replace(self.data, status=status))
            elif msg.topic == TOPIC_WORKING_STATUS:
                working = decode_working_status(msg.payload)
                self.async_set_updated_data(replace(self.data, working=working))
            elif msg.topic == TOPIC_TIME_LINE:
                self._add_timeline(decode_timeline(msg.payload))
            elif msg.topic == TOPIC_CLEAN_REPORT:
                report = decode_clean_report(msg.payload)
                self.async_set_updated_data(replace(self.data, last_report=report))
        except ValueError:
            _LOGGER.debug("Undecodable push on %s: %s", msg.topic, msg.payload.hex())

    @callback
    def _handle_display_map(self, payload: bytes) -> None:
        robot = decode_display_map(payload).robot
        if robot is None:
            return
        live = self.live
        point = (robot.x, robot.y)
        if not live.path or math.dist(live.path[-1], point) >= PATH_MIN_STEP:
            live.path.append(point)
            if len(live.path) > PATH_MAX_POINTS:
                del live.path[: len(live.path) - PATH_MAX_POINTS]
        if robot == live.robot:
            return
        live.robot = robot
        live.version += 1
        for listener in list(self._live_listeners):
            listener()

    @callback
    def _add_timeline(self, events: list[TimelineEvent]) -> None:
        """Pushes carry only new events; a self check that opens a task
        starts a fresh timeline."""
        timeline = list(self.data.timeline)
        for event in events:
            if event.primary and event.task is PrimaryTask.SELF_CHECK and not any(
                e.task is PrimaryTask.SELF_CHECK for e in timeline[-3:]
            ):
                timeline = []
            if event not in timeline:
                timeline.append(event)
        timeline.sort(key=lambda e: e.time)
        self.async_set_updated_data(replace(self.data, timeline=tuple(timeline[-TIMELINE_MAX:])))

    @callback
    def _track_clean_start(self, old: RobotBaseStatus | None, new: RobotBaseStatus) -> None:
        """Start a fresh path when a cleaning job begins."""
        if new.in_clean_task and (old is None or not old.in_clean_task):
            self.live.path.clear()
            self.live.version += 1

    @callback
    def async_add_live_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call `listener` whenever the robot moves. Returns an unsubscribe."""
        self._live_listeners.append(listener)
        return lambda: self._live_listeners.remove(listener)

    # --- connection -------------------------------------------------------

    @callback
    def _handle_disconnect(self) -> None:
        """The robot drops the connection now and then (seen five times in a
        20-minute clean); reconnect quietly and only report the entities
        unavailable when that fails."""
        if self._reconnecting:
            return
        self._reconnecting = True
        self.config_entry.async_create_background_task(
            self.hass, self._async_reconnect(), "narwal_local reconnect"
        )

    async def _async_reconnect(self) -> None:
        try:
            for delay in RECONNECT_DELAYS:
                if delay:
                    await asyncio.sleep(delay)
                try:
                    await self.robot.connect()
                    await self.robot.activate_reporting(REPORT_SECONDS)
                except NarwalError as err:
                    _LOGGER.debug("Reconnect to %s failed: %s", self.robot.host, err)
                    continue
                _LOGGER.debug("Reconnected to %s", self.robot.host)
                return
            self.async_set_update_error(UpdateFailed("connection lost"))
        finally:
            self._reconnecting = False

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
