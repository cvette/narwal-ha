"""Battery health sensors."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import FakeRobot


async def test_battery_sensors(hass: HomeAssistant, init_integration) -> None:
    assert hass.states.get("sensor.narwal_battery_health").state == "100"
    assert hass.states.get("sensor.narwal_battery_charge_cycles").state == "80"
    assert hass.states.get("sensor.narwal_battery_capacity").state == "6063"
    assert hass.states.get("sensor.narwal_battery_temperature").state == "27.3"
    registry = er.async_get(hass)
    voltage = registry.async_get("sensor.narwal_battery_voltage")
    assert voltage.disabled_by is er.RegistryEntryDisabler.INTEGRATION, "voltage and current start disabled"
    assert registry.async_get("sensor.narwal_battery_health").entity_category == "diagnostic"


async def test_no_battery_sensors_without_the_feature(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    robot.features.flags["supportBatteryHealthInfo"] = False
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.narwal_battery_health") is None
    assert hass.states.get("sensor.narwal_battery") is not None
