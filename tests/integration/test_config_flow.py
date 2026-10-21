"""Config flow."""

from __future__ import annotations

from collections.abc import Generator
from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.narwal_local.const import DOMAIN

from .conftest import DEVICE_ID, FakeRobot


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep the created entry from being set up, so only the flow is tested."""
    with patch("custom_components.narwal_local.async_setup_entry", return_value=True) as mock:
        yield mock


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_creates_entry(hass: HomeAssistant, robot: FakeRobot) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.113"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Narwal"
    assert result["data"] == {CONF_HOST: "192.168.1.113", CONF_PORT: 9002}
    assert result["result"].unique_id == DEVICE_ID
    assert not robot.connected, "validation must close its connection"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_recovers_from_cannot_connect(hass: HomeAssistant, robot: FakeRobot) -> None:
    robot.fail_connect = True
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    robot.fail_connect = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.113"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_same_robot_updates_host(
    hass: HomeAssistant, robot: FakeRobot, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.200"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.168.1.200"


async def test_reconfigure_changes_host(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    result = await init_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_PORT: 9002}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data[CONF_HOST] == "192.168.1.50"


async def test_reconfigure_rejects_other_robot(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    result = await init_integration.start_reconfigure_flow(hass)
    robot.device.device_id = "f" * 32
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.51", CONF_PORT: 9002}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert init_integration.data[CONF_HOST] == "192.168.1.113"


def _discovery(ip: str = "192.168.1.113") -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(ip),
        ip_addresses=[ip_address(ip)],
        hostname="narwal.local.",
        name="narwal._narwal_sweeper._tcp.local.",
        port=5000,
        type="_narwal_sweeper._tcp.local.",
        properties={},
    )


@pytest.mark.usefixtures("mock_setup_entry")
async def test_zeroconf_discovery_creates_entry(hass: HomeAssistant, robot: FakeRobot) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_discovery()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert robot.port == 9002, "the advertised port is not used"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.168.1.113", CONF_PORT: 9002}
    assert result["result"].unique_id == DEVICE_ID


async def test_zeroconf_updates_host_of_known_robot(
    hass: HomeAssistant, robot: FakeRobot, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_discovery("192.168.1.77")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.168.1.77"


async def test_zeroconf_unreachable_aborts(hass: HomeAssistant, robot: FakeRobot) -> None:
    robot.fail_connect = True
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_discovery()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
