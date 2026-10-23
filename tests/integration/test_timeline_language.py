"""Last-event sensor (timeline), voice language, restart button."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.narwal_local.const import POLL_INTERVAL
from custom_components.narwal_local.protocol import Language, PrimaryTask, TimelineEvent

from .conftest import FakeRobot, timeline_payload

LAST_EVENT = "sensor.narwal_last_event"
T0 = 1792598355.0


async def test_last_event_from_pushes(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    assert hass.states.get(LAST_EVENT).state == "unknown", "the robot kept no timeline"
    robot.push("/status/time_line_status", timeline_payload((T0, 1, None, None)))
    robot.push("/status/time_line_status", timeline_payload((T0 + 60, 4, 1, 1)))  # living room started
    await hass.async_block_till_done()
    state = hass.states.get(LAST_EVENT)
    assert state.state == "start"
    assert state.attributes["events"][-1]["room"] == "Living room"
    assert [e["event"] for e in state.attributes["events"]] == ["self_check", "start"]


async def test_empty_poll_keeps_the_timeline(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer: FrozenDateTimeFactory
) -> None:
    robot.push("/status/time_line_status", timeline_payload((T0, 9, None, None)))
    await hass.async_block_till_done()
    freezer.tick(POLL_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(LAST_EVENT).state == "dust_gather"

    robot.timeline = [TimelineEvent(T0 + 5, PrimaryTask.FINISHED, primary=True)]
    freezer.tick(POLL_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(LAST_EVENT).state == "finished", "the robot's list wins when it has one"


async def test_voice_language(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    select = "select.narwal_voice_language"
    state = hass.states.get(select)
    assert state.state == "english"
    assert state.attributes["options"] == ["spanish", "japanese", "french", "english"]
    await hass.services.async_call("select", "select_option", {ATTR_ENTITY_ID: select, "option": "french"}, blocking=True)
    assert robot.calls[-1] == ("set_language", Language.FRENCH)
    assert hass.states.get(select).state == "french"


async def test_restart_button(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: "button.narwal_restart"}, blocking=True)
    assert robot.calls[-1] == ("reboot",)
