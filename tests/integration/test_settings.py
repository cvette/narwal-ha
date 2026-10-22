"""Settings entities (switch, select, number, time) and the clean-finished event."""

from __future__ import annotations

from datetime import UTC, datetime, time

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.select import ATTR_OPTION, ATTR_OPTIONS, SERVICE_SELECT_OPTION
from homeassistant.components.switch import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.components.time import ATTR_TIME
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.narwal_local.protocol import CarpetStrategy, DisturbMode, Setting

from .conftest import FakeRobot, clean_report_payload

DND = "switch.narwal_do_not_disturb"
EVENT = "event.narwal_clean_finished"


async def _call(hass: HomeAssistant, domain: str, service: str, entity: str, **data) -> None:
    await hass.services.async_call(domain, service, {ATTR_ENTITY_ID: entity, **data}, blocking=True)


async def test_settings_from_the_robot(hass: HomeAssistant, init_integration) -> None:
    assert hass.states.get("number.narwal_volume").state == "20"
    assert hass.states.get(DND).state == STATE_ON
    assert hass.states.get("time.narwal_do_not_disturb_start").state == "22:00:00"
    assert hass.states.get("time.narwal_do_not_disturb_end").state == "08:00:00"
    expected = {
        "child_lock": STATE_OFF,
        "auto_empty": STATE_ON,
        "quiet_auto_empty": STATE_OFF,
        "dust_bag_drying": STATE_ON,
        "automatic_detergent": STATE_ON,
        "hot_water_mop_wash": STATE_ON,
    }
    for key, state in expected.items():
        assert hass.states.get(f"switch.narwal_{key}").state == state, key
    entry = er.async_get(hass).async_get("switch.narwal_child_lock")
    assert entry.entity_category == "config"


async def test_switch_writes_and_reads_back(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _call(hass, "switch", SERVICE_TURN_ON, "switch.narwal_child_lock")
    assert robot.calls[-1] == ("set_config", Setting.CHILD_LOCK, True)
    assert hass.states.get("switch.narwal_child_lock").state == STATE_ON

    await _call(hass, "switch", SERVICE_TURN_OFF, "switch.narwal_auto_empty")
    assert robot.calls[-1] == ("set_config", Setting.DUST_GATHERING, False)
    assert hass.states.get("switch.narwal_auto_empty").state == STATE_OFF


async def test_do_not_disturb_keeps_its_times(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _call(hass, "switch", SERVICE_TURN_OFF, DND)
    assert robot.calls[-1] == ("set_config", Setting.DO_NOT_DISTURB, DisturbMode(False, time(22), time(8)))
    assert hass.states.get(DND).state == STATE_OFF

    await _call(hass, "time", "set_value", "time.narwal_do_not_disturb_start", **{ATTR_TIME: "21:30:00"})
    assert robot.calls[-1] == ("set_config", Setting.DO_NOT_DISTURB, DisturbMode(False, time(21, 30), time(8)))
    assert hass.states.get("time.narwal_do_not_disturb_start").state == "21:30:00"
    assert hass.states.get(DND).state == STATE_OFF, "changing a time does not switch it on"


async def test_volume(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _call(hass, "number", SERVICE_SET_VALUE, "number.narwal_volume", **{ATTR_VALUE: 45})
    assert robot.calls[-1] == ("set_config", Setting.VOLUME, 45)
    assert hass.states.get("number.narwal_volume").state == "45"


async def test_no_settings_entities_without_config(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    robot.config_supported = False
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("vacuum.narwal") is not None
    assert hass.states.get("number.narwal_volume") is None
    assert hass.states.get(DND) is None


async def test_switches_follow_feature_flags(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    robot.features.flags["supportHotWaterWash"] = False
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("switch.narwal_hot_water_mop_wash") is None
    assert hass.states.get("switch.narwal_quiet_auto_empty") is not None


async def test_clean_finished_event(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    assert hass.states.get(EVENT).state == STATE_UNKNOWN
    end = 1792600025
    robot.push("/report/clean_report", clean_report_payload(16.0092, 1112, end - 1671, end))
    await hass.async_block_till_done()
    state = hass.states.get(EVENT)
    assert state.attributes["event_type"] == "completed"
    assert state.attributes["result"] == "normal_end"
    assert state.attributes["clean_type"] == "vacuum_and_mop"
    assert state.attributes["area"] == 16.0
    assert state.attributes["duration"] == 1112
    assert state.attributes["end"] == datetime.fromtimestamp(end, UTC).isoformat()
    fired_at = state.state

    # A poll keeps the same report: no second event.
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(EVENT).state == fired_at

    robot.push("/report/clean_report", clean_report_payload(0, 0, end, end + 16, task_type=6, result=2))
    await hass.async_block_till_done()
    state = hass.states.get(EVENT)
    assert state.attributes["event_type"] == "stopped"
    assert state.attributes["clean_type"] == "custom"


async def test_more_setting_switches(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    expected = {
        "deep_clean_heavy_dirt": STATE_ON,
        "pet_mode": STATE_OFF,
        "carpets_first": STATE_OFF,
        "deep_carpet_cleaning": STATE_OFF,
        "station_light": STATE_ON,
    }
    for key, state in expected.items():
        assert hass.states.get(f"switch.narwal_{key}").state == state, key

    await _call(hass, "switch", SERVICE_TURN_OFF, "switch.narwal_station_light")
    assert robot.calls[-1] == ("set_config", Setting.STATION_LIGHT, False)
    assert hass.states.get("switch.narwal_station_light").state == STATE_OFF


async def test_setting_selects(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    expected = {
        "carpets": "boost",
        "mop_drying": "quiet",
        "mop_washing": "normal",
        "corner_cleaning": "flexible_mop",
        "obstacle_avoidance": "smart",
    }
    for key, option in expected.items():
        assert hass.states.get(f"select.narwal_{key}").state == option, key
    assert hass.states.get("select.narwal_carpets").attributes[ATTR_OPTIONS] == [
        "cross", "boost", "ignore", "avoid"
    ]  # fmt: skip

    await _call(hass, "select", SERVICE_SELECT_OPTION, "select.narwal_carpets", **{ATTR_OPTION: "avoid"})
    assert robot.calls[-1] == ("set_config", Setting.CARPET_STRATEGY, CarpetStrategy.AVOID)
    assert hass.states.get("select.narwal_carpets").state == "avoid"


async def test_options_follow_feature_flags(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    robot.features.flags["supportFlexibleMop"] = False
    robot.features.flags["supportAvoidModeConfig"] = False
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("select.narwal_obstacle_avoidance") is None
    corner = hass.states.get("select.narwal_corner_cleaning")
    assert corner.attributes[ATTR_OPTIONS] == ["turn_robot", "off"]
    assert corner.state == "unknown", "the robot's value is not offered here"


async def test_settings_the_robot_does_not_report(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    robot.config.reported.discard(Setting.CARPET_FIRST)
    robot.config.reported.discard(Setting.MOP_DRYING)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("switch.narwal_carpets_first") is None
    assert hass.states.get("select.narwal_mop_drying") is None
    assert hass.states.get("select.narwal_mop_washing") is not None
