"""Async client for the robot's local WebSocket (ws://<ip>:9002).

One connection carries requests, their replies (matched by
Header.properties.correlationData) and unsolicited pushes. No authentication
or /<pid>/<did> topic prefix is needed on the LAN.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from dataclasses import dataclass
import logging
import uuid

import aiohttp

from .enums import FanLevel, FirmwareStatus, MopHumidity, ServiceResult
from .frame import SOURCE_APP, FrameError, Header, decode_frame, encode_frame, topic_of
from .map import MapInfo, decode_get_map_response
from .models import (
    ConsumableInfo,
    DeviceInfo,
    FeatureList,
    FirmwareVersion,
    RobotBaseStatus,
    decode_check_firmware,
    decode_consumable_info,
    decode_device_base_status,
    decode_device_info,
    decode_feature_list,
    decode_firmware_version,
    decode_result,
)
from .pb import ProtobufError, Writer

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 9002
DEFAULT_TIMEOUT = 30.0  # seconds; the app waits about as long

# Push topics (after topic_of strips the /<pid>/<did> prefix).
TOPIC_ROBOT_BASE_STATUS = "/status/robot_base_status"
TOPIC_WORKING_STATUS = "/status/working_status"
TOPIC_DISPLAY_MAP = "/map/display_map"
TOPIC_DOWNLOAD_STATUS = "/status/download_status"
TOPIC_UPGRADE_STATUS = "/upgrade/upgrade_status"


class NarwalError(Exception):
    """Base error."""


class NarwalConnectionError(NarwalError):
    """The robot is unreachable or the connection dropped."""


class NarwalTimeoutError(NarwalError):
    """The robot did not answer in time."""


class NarwalCommandError(NarwalError):
    """The robot answered a command with a failure result."""

    def __init__(self, url: str, result: ServiceResult | int) -> None:
        name = result.name if isinstance(result, ServiceResult) else str(result)
        super().__init__(f"{url}: {name}")
        self.url = url
        self.result = result


@dataclass(slots=True)
class Message:
    """One inbound frame."""

    header: Header
    payload: bytes

    @property
    def topic(self) -> str:
        return topic_of(self.header.url)


PushCallback = Callable[[Message], None]


class NarwalClient:
    """Low-level connection: connect, call, receive pushes."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._session = session
        self._own_session = session is None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[Message]] = {}
        self._push_callbacks: list[PushCallback] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        self._write_lock = asyncio.Lock()

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}/"

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    # --- lifecycle ------------------------------------------------------

    async def connect(self) -> None:
        if self.connected:
            return
        if self._session is None:
            self._session = aiohttp.ClientSession()
        try:
            async with asyncio.timeout(self.timeout):
                self._ws = await self._session.ws_connect(
                    self.url, timeout=aiohttp.ClientWSTimeout(ws_close=10), heartbeat=None
                )
        except TimeoutError as err:
            raise NarwalConnectionError(f"timeout connecting to {self.url}") from err
        except (aiohttp.ClientError, OSError) as err:
            raise NarwalConnectionError(f"cannot connect to {self.url}: {err}") from err
        self._reader = asyncio.create_task(self._read_loop(self._ws), name="narwal-reader")

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            await ws.close()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None
        self._fail_pending(NarwalConnectionError("connection closed"))
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> NarwalClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # --- subscriptions --------------------------------------------------

    def add_push_callback(self, cb: PushCallback) -> Callable[[], None]:
        """Call cb for every push. Returns a function that unsubscribes."""
        self._push_callbacks.append(cb)
        return lambda: self._push_callbacks.remove(cb)

    def add_disconnect_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Call cb once the connection drops (not after close())."""
        self._disconnect_callbacks.append(cb)
        return lambda: self._disconnect_callbacks.remove(cb)

    # --- requests -------------------------------------------------------

    async def call(self, service_url: str, request: bytes = b"", *, timeout: float | None = None) -> Message:
        """Send a service request and wait for its reply."""
        if not service_url.startswith("/"):
            service_url = "/" + service_url
        ws = self._ws
        if ws is None or ws.closed:
            raise NarwalConnectionError("not connected")
        corr = uuid.uuid4().hex
        header = Header(
            url=service_url,
            uuid=corr,
            source=SOURCE_APP,
            response_url=service_url + "/response",
            correlation_data=corr,
        )
        fut: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        self._pending[corr] = fut
        try:
            async with self._write_lock:
                await ws.send_bytes(encode_frame(header.marshal(), request))
            async with asyncio.timeout(timeout or self.timeout):
                return await fut
        except TimeoutError as err:
            raise NarwalTimeoutError(f"no reply to {service_url}") from err
        except (aiohttp.ClientError, ConnectionResetError) as err:
            raise NarwalConnectionError(f"send {service_url}: {err}") from err
        finally:
            self._pending.pop(corr, None)

    async def publish(self, service_url: str, request: bytes = b"") -> None:
        """Fire-and-forget send (the app does this for joystick velocity)."""
        ws = self._ws
        if ws is None or ws.closed:
            raise NarwalConnectionError("not connected")
        header = Header(url=service_url, uuid=uuid.uuid4().hex, source=SOURCE_APP)
        async with self._write_lock:
            await ws.send_bytes(encode_frame(header.marshal(), request))

    # --- receive --------------------------------------------------------

    async def _read_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    self._dispatch(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            if self._ws is ws:  # dropped, not closed by us
                self._ws = None
                self._fail_pending(NarwalConnectionError("connection lost"))
                for cb in list(self._disconnect_callbacks):
                    cb()

    def _dispatch(self, data: bytes) -> None:
        try:
            hb, payload = decode_frame(data)
            header = Header.parse(hb)
        except (FrameError, ProtobufError) as err:
            _LOGGER.debug("ignoring undecodable frame: %s", err)
            return
        msg = Message(header, payload)
        corr = header.correlation_data or header.uuid
        fut = self._pending.get(corr)
        if fut is not None:
            if not fut.done():
                fut.set_result(msg)
            return
        for cb in list(self._push_callbacks):
            try:
                cb(msg)
            except Exception:
                _LOGGER.exception("push callback failed for %s", msg.topic)

    def _fail_pending(self, err: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(err)
        self._pending.clear()


class NarwalRobot(NarwalClient):
    """Typed service calls on top of NarwalClient.

    Commands that change robot state (dock, pause, fan level, …) act on the
    physical robot. Only calls verified on a real robot are exposed here;
    starting a clean, room cleaning, stop and locate follow once verified.
    """

    async def _command(self, url: str, request: bytes = b"") -> ServiceResult | int:
        result = decode_result((await self.call(url, request)).payload)
        if result != ServiceResult.PERFORM_SUCCESS:
            raise NarwalCommandError(url, result)
        return result

    # read-only

    async def get_status(self) -> RobotBaseStatus:
        return decode_device_base_status((await self.call("/status/get_device_base_status")).payload)

    async def get_device_info(self) -> DeviceInfo:
        return decode_device_info((await self.call("/common/get_device_info")).payload)

    async def get_features(self) -> FeatureList:
        return decode_feature_list((await self.call("/common/get_feature_list")).payload)

    async def get_consumables(self) -> ConsumableInfo:
        return decode_consumable_info((await self.call("/consumable/get_consumable_info")).payload)

    async def get_firmware_version(self) -> FirmwareVersion:
        return decode_firmware_version((await self.call("/common/upgrade/get_firmware_version")).payload)

    async def check_firmware(self) -> FirmwareStatus | int:
        """Whether the robot has already downloaded an update (it fetches them itself)."""
        return decode_check_firmware((await self.call("/common/upgrade/check_firmware")).payload)

    async def get_map(self) -> MapInfo:
        """Current map as COMPRESSED_GRID (the protobuf default request)."""
        return decode_get_map_response((await self.call("/map/get_map")).payload)

    async def activate_reporting(self, seconds: int = 60) -> ServiceResult | int:
        """Ask the robot to push status topics for `seconds`; re-send before it
        lapses. Request {1 topicsDuration{1 workStatus, 2 displayMap,
        3 robotBaseStatus}, 2 publishDuration}."""
        topics = Writer().varint(1, seconds).varint(2, seconds).varint(3, seconds)
        req = Writer().message(1, topics).varint(2, seconds)
        return decode_result((await self.call("/common/active_robot_publish", bytes(req))).payload)

    # state-changing (verified)

    async def dock(self) -> None:
        """Return to the station (/supply/recall)."""
        await self._command("/supply/recall")

    async def pause(self, *task_ids: int) -> None:
        """Pause the given tasks, or all current tasks."""
        await self._command("/task/pause", _repeated_int64(task_ids))

    async def resume(self, *task_ids: int) -> None:
        await self._command("/task/resume", _repeated_int64(task_ids))

    async def set_fan_level(self, level: FanLevel) -> None:
        await self._command("/clean/set_fan_level", bytes(Writer().int32(1, int(level), force=True)))

    async def set_mop_humidity(self, humidity: MopHumidity) -> None:
        await self._command("/clean/set_mop_humidity", bytes(Writer().int32(1, int(humidity), force=True)))


def _repeated_int64(values: tuple[int, ...]) -> bytes:
    w = Writer()
    for v in values:
        w.varint(1, v, force=True)
    return bytes(w)
