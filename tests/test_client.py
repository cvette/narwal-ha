"""Client against a fake robot served by aiohttp."""

from __future__ import annotations

import asyncio

from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer
import pytest

from protocol.client import (
    TOPIC_ROBOT_BASE_STATUS,
    NarwalCommandError,
    NarwalConnectionError,
    NarwalRobot,
    NarwalTimeoutError,
)
from protocol.enums import FanLevel, ServiceResult
from protocol.frame import Header, decode_frame, encode_frame
from protocol.pb import Writer, parse

# The fake robot is a real local WebSocket server.
pytestmark = pytest.mark.usefixtures("socket_enabled")

PUSH_URL ="/pid0000000/0123456789abcdef0123456789abcdef/status/robot_base_status"


class FakeRobot:
    """Answers like the robot: reply on <url>/response echoing correlationData."""

    def __init__(self, fixture_bin) -> None:
        self.fixture_bin = fixture_bin
        self.requests: list[tuple[str, bytes]] = []
        self.sockets: list[web.WebSocketResponse] = []
        self.replies: dict[str, bytes] = {
            "/status/get_device_base_status": fixture_bin("device_base_status"),
            "/map/get_map": fixture_bin("get_map"),
            "/supply/recall": bytes(Writer().varint(1, ServiceResult.ROBOT_IN_STATION_WHEN_RECALL)),
        }

    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        async for msg in ws:
            if msg.type != WSMsgType.BINARY:
                continue
            hb, payload = decode_frame(msg.data)
            req = Header.parse(hb)
            self.requests.append((req.url, payload))
            if req.url == "/never/answers":
                continue
            if req.url == "/common/active_robot_publish":
                push = Header(url=PUSH_URL, uuid="push-1")
                await ws.send_bytes(encode_frame(push.marshal(), self.fixture_bin("push_status_robot_base_status")))
            reply = self.replies.get(req.url, bytes(Writer().varint(1, ServiceResult.PERFORM_SUCCESS)))
            resp = Header(url=req.url + "/response", uuid=req.uuid, correlation_data=req.correlation_data)
            await ws.send_bytes(encode_frame(resp.marshal(), reply))
        return ws


@pytest.fixture
async def robot_server(fixture_bin):
    fake = FakeRobot(fixture_bin)
    app = web.Application()
    app.router.add_get("/", fake.handler)
    server = TestServer(app)
    await server.start_server()
    yield fake, server
    await server.close()


@pytest.fixture
async def robot(robot_server):
    _, server = robot_server
    client = NarwalRobot(server.host, server.port, timeout=2)
    await client.connect()
    yield client
    await client.close()


async def test_get_status_and_map(robot) -> None:
    st = await robot.get_status()
    assert st.battery == 100 and st.has_station
    mi = await robot.get_map()
    assert [r.name for r in mi.rooms] == ["Living room", "Kitchen", "Hallway", "Bedroom"]


async def test_concurrent_calls_are_matched_by_correlation(robot) -> None:
    results = await asyncio.gather(*(robot.get_status() for _ in range(10)))
    assert all(r.map_id == 1 for r in results)


async def test_push_reaches_callback_with_prefix_stripped(robot) -> None:
    got = []
    robot.add_push_callback(got.append)
    assert await robot.activate_reporting(60) is ServiceResult.PERFORM_SUCCESS
    assert [m.topic for m in got] == [TOPIC_ROBOT_BASE_STATUS]


async def test_activate_reporting_request_layout(robot, robot_server) -> None:
    fake, _ = robot_server
    await robot.activate_reporting(45)
    url, payload = fake.requests[-1]
    assert url == "/common/active_robot_publish"
    top = {f.num: f for f in parse(payload)}
    assert top[2].int == 45
    assert {f.num: f.int for f in parse(top[1].data)} == {1: 45, 2: 45, 3: 45}


async def test_command_failure_raises(robot) -> None:
    with pytest.raises(NarwalCommandError) as err:
        await robot.dock()
    assert err.value.result is ServiceResult.ROBOT_IN_STATION_WHEN_RECALL


async def test_set_fan_level_sends_enum(robot, robot_server) -> None:
    fake, _ = robot_server
    await robot.set_fan_level(FanLevel.STRONG)
    assert fake.requests[-1] == ("/clean/set_fan_level", b"\x08\x03")


async def test_timeout(robot) -> None:
    with pytest.raises(NarwalTimeoutError):
        await robot.call("/never/answers", timeout=0.2)


async def test_connection_loss_fails_pending_and_notifies(robot, robot_server) -> None:
    fake, _ = robot_server
    lost = asyncio.Event()
    robot.add_disconnect_callback(lost.set)
    pending = asyncio.create_task(robot.call("/never/answers", timeout=5))
    await asyncio.sleep(0.1)
    await fake.sockets[0].close()
    with pytest.raises(NarwalConnectionError):
        await pending
    await asyncio.wait_for(lost.wait(), 2)
    assert not robot.connected
    with pytest.raises(NarwalConnectionError):
        await robot.get_status()


async def test_unreachable_host() -> None:
    client = NarwalRobot("127.0.0.1", 1, timeout=2)
    with pytest.raises(NarwalConnectionError):
        await client.connect()
    await client.close()
