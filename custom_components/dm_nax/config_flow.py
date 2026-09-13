"""Config flow for Crestron DM NAX."""

from __future__ import annotations

from typing import Any

from aiohttp import CookieJar
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers import selector

from .api import DmNaxApi, DmNaxApiError, DmNaxAuthError
from .const import CONF_USE_SSL, CONF_VERIFY_SSL, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL, DOMAIN


class DmNaxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a DM NAX config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _async_validate_input(self.hass, user_input)
            except DmNaxAuthError:
                errors["base"] = "invalid_auth"
            except DmNaxApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_USERNAME, default="admin"): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_USE_SSL, default=True): bool,
                    vol.Optional(CONF_VERIFY_SSL, default=False): bool,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ): int,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return DmNaxOptionsFlow(config_entry)


class DmNaxOptionsFlow(config_entries.OptionsFlow):
    """Handle DM NAX options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options or self.config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current.get(
                            CONF_SCAN_INTERVAL,
                            int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                        ),
                    ): int,
                }
            ),
        )


async def _async_validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, str]:
    """Validate credentials and return config entry metadata."""
    session = async_create_clientsession(
        hass,
        verify_ssl=data.get(CONF_VERIFY_SSL, False),
        cookie_jar=CookieJar(unsafe=True),
    )
    api = DmNaxApi(
        session,
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        use_ssl=data.get(CONF_USE_SSL, True),
        verify_ssl=data.get(CONF_VERIFY_SSL, False),
    )
    try:
        device_info = (await api.async_get("/Device/DeviceInfo")).get("Device", {}).get(
            "DeviceInfo",
            {},
        )
    finally:
        await api.async_close()

    unique_id = str(
        device_info.get("DeviceId")
        or device_info.get("SerialNumber")
        or data[CONF_HOST].strip().lower()
    )
    title = str(device_info.get("Name") or device_info.get("Model") or DEFAULT_NAME)
    return {"unique_id": unique_id, "title": title}
