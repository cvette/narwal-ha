"""Config flow: the robot's LAN address, checked by reading its device info."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT, DOMAIN
from .protocol import DeviceInfo, NarwalError, NarwalRobot

_LOGGER = logging.getLogger(__name__)

VALIDATE_TIMEOUT = 10.0


def _schema(host: str = "", port: int = DEFAULT_PORT) -> vol.Schema:
    host_key = vol.Required(CONF_HOST, default=host) if host else vol.Required(CONF_HOST)
    return vol.Schema(
        {
            host_key: str,
            vol.Optional(CONF_PORT, default=port): vol.All(int, vol.Range(min=1, max=65535)),
        }
    )


class NarwalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Narwal robot by IP address."""

    VERSION = 1

    async def _validate(self, user_input: dict[str, Any]) -> tuple[DeviceInfo | None, dict[str, str]]:
        robot = NarwalRobot(
            user_input[CONF_HOST],
            user_input[CONF_PORT],
            session=async_get_clientsession(self.hass),
            timeout=VALIDATE_TIMEOUT,
        )
        try:
            await robot.connect()
            device = await robot.get_device_info()
            await robot.get_status()
        except NarwalError as err:
            _LOGGER.debug("Cannot reach %s: %s", user_input[CONF_HOST], err)
            return None, {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error talking to %s", user_input[CONF_HOST])
            return None, {"base": "unknown"}
        finally:
            await robot.close()
        if not device.device_id:
            return None, {"base": "unknown"}
        return device, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device, errors = await self._validate(user_input)
            if device is not None:
                await self.async_set_unique_id(device.device_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]}
                )
                return self.async_create_entry(title="Narwal", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_schema(), user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            device, errors = await self._validate(user_input)
            if device is not None:
                await self.async_set_unique_id(device.device_id)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)),
            errors=errors,
        )
