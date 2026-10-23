"""Config flow: the robot's LAN address, checked by reading its device info.

Robots are also discovered over mDNS (_narwal_sweeper._tcp, the service the
Narwal app browses for). The WebSocket port is fixed, so a discovered robot
is reached on DEFAULT_PORT whatever port the service advertises.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DEFAULT_PORT, DOMAIN
from .floorplan import CONF_FLOORPLAN, Affine
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

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NarwalOptionsFlow:
        return NarwalOptionsFlow()

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

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        user_input = {CONF_HOST: str(discovery_info.ip_address), CONF_PORT: DEFAULT_PORT}
        device, _errors = await self._validate(user_input)
        if device is None:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(device.device_id)
        # A robot that is already set up just gets its new address.
        self._abort_if_unique_id_configured(updates=user_input)
        self._discovered = user_input
        self.context["title_placeholders"] = {"host": user_input[CONF_HOST]}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Narwal", data=self._discovered)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"host": self._discovered[CONF_HOST]},
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


# Floor plan calibration: three reference points, each a map position in
# metres and the same spot on the floor plan.
POINT_FIELDS = ("map_x", "map_y", "plan_x", "plan_y")
FIELDS = [f"p{i}_{name}" for i in (1, 2, 3) for name in POINT_FIELDS]
NUMBER = NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, step="any"))


class NarwalOptionsFlow(OptionsFlowWithReload):
    """Floor plan calibration; leave every field empty to turn it off."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            values = [user_input.get(name) for name in FIELDS]
            if all(v is None for v in values):
                return self.async_create_entry(data={})
            if any(v is None for v in values):
                errors["base"] = "incomplete_points"
            else:
                pairs = [values[i : i + 4] for i in range(0, 12, 4)]
                try:
                    Affine.from_points(pairs)
                except ValueError:
                    errors["base"] = "points_on_a_line"
                else:
                    return self.async_create_entry(data={CONF_FLOORPLAN: pairs})
        current = user_input
        if current is None and (pairs := self.config_entry.options.get(CONF_FLOORPLAN)):
            current = dict(zip(FIELDS, (v for p in pairs for v in p), strict=True))
        schema = vol.Schema({vol.Optional(name): NUMBER for name in FIELDS})
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current or {}),
            errors=errors,
        )
