"""Config flow for Crestron DM NAX."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import DmNaxApi, DmNaxApiError, DmNaxAuthError
from .const import (
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .media import validate_credentials

_OPTIONS_DESCRIPTION_PLACEHOLDERS = {
    "setup_url": (
        "https://github.com/Phant0mElit3/ha-dm-nax/blob/main/"
        "docs/MEDIA_AND_AUTOMATION.md#optional-media-player-2"
    ),
}


class DmNaxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a DM NAX config flow."""

    VERSION = 1
    MINOR_VERSION = 2

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
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional(CONF_USE_SSL, default=True): bool,
                    vol.Optional(CONF_VERIFY_SSL, default=False): bool,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Repair credentials for an existing device."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Validate replacement credentials before updating the entry."""
        return await self._async_update_connection("reauth_confirm", user_input)

    async def async_step_reconfigure(self, user_input=None):
        """Change the host or connection settings without replacing entities."""
        return await self._async_update_connection("reconfigure", user_input)

    async def _async_update_connection(self, step_id, user_input):
        entry = (
            self._get_reauth_entry()
            if step_id == "reauth_confirm"
            else self._get_reconfigure_entry()
        )
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if not user_input.get(CONF_PASSWORD):
                data[CONF_PASSWORD] = entry.data[CONF_PASSWORD]
            try:
                info = await _async_validate_input(self.hass, data)
            except DmNaxAuthError:
                errors["base"] = "invalid_auth"
            except DmNaxApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=data)

        fields = {}
        if step_id == "reconfigure":
            fields[vol.Required(CONF_HOST, default=entry.data[CONF_HOST])] = str
            fields[
                vol.Optional(CONF_USE_SSL, default=entry.data.get(CONF_USE_SSL, True))
            ] = bool
            fields[
                vol.Optional(
                    CONF_VERIFY_SSL, default=entry.data.get(CONF_VERIFY_SSL, False)
                )
            ] = bool
        fields[vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME])] = str
        password_key = vol.Required if step_id == "reauth_confirm" else vol.Optional
        fields[password_key(CONF_PASSWORD)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
        return self.async_show_form(
            step_id=step_id, data_schema=vol.Schema(fields), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return DmNaxOptionsFlow()


class DmNaxOptionsFlow(config_entries.OptionsFlow):
    """Handle DM NAX options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Manage options."""
        if user_input is not None:
            try:
                aliases = user_input.get("stream_aliases", {})
                if not isinstance(aliases, dict):
                    raise TypeError
                normalized_aliases = {
                    str(ip_address(key)): _alias(value)
                    for key, value in aliases.items()
                }
                if "stream_aliases" in user_input:
                    user_input["stream_aliases"] = normalized_aliases
            except (ValueError, TypeError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(),
                    errors={"base": "invalid_aliases"},
                    description_placeholders=_OPTIONS_DESCRIPTION_PLACEHOLDERS,
                )
            data = {**self.config_entry.options, **user_input}
            if not user_input.get("media_client_secret"):
                data["media_client_secret"] = self.config_entry.options.get(
                    "media_client_secret", ""
                )
                if not data["media_client_secret"]:
                    data.pop("media_client_secret")
            if data.get("enable_media_player"):
                try:
                    validate_credentials(
                        data.get("media_client_id", ""),
                        data.get("media_client_secret", ""),
                    )
                    if not self.config_entry.data.get(CONF_USE_SSL, True):
                        raise ValueError("Media Player 2 requires HTTPS")
                except (ValueError, TypeError):
                    return self.async_show_form(
                        step_id="init",
                        data_schema=self._schema(),
                        errors={"base": "invalid_media_credentials"},
                        description_placeholders=_OPTIONS_DESCRIPTION_PLACEHOLDERS,
                    )
            return self.async_create_entry(title="", data=data)

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(),
            description_placeholders=_OPTIONS_DESCRIPTION_PLACEHOLDERS,
        )

    def _schema(self):
        current = self.config_entry.options or self.config_entry.data
        return vol.Schema(
            {
                vol.Optional(
                    "enable_media_player",
                    default=current.get("enable_media_player", False),
                ): bool,
                vol.Optional(
                    "media_client_id", default=current.get("media_client_id", "")
                ): str,
                vol.Optional("media_client_secret"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    "stream_aliases", default=current.get("stream_aliases", {})
                ): selector.ObjectSelector(),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(
                        CONF_SCAN_INTERVAL,
                        int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }
        )


def _alias(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= 60
        or not value.isprintable()
    ):
        raise ValueError("Invalid stream alias")
    return value.strip()


async def _async_validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, str]:
    """Validate credentials and return config entry metadata."""
    session = async_create_clientsession(
        hass,
        verify_ssl=data.get(CONF_VERIFY_SSL, False),
        cookie_jar=CookieJar(unsafe=True),
        auto_cleanup=False,
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
        device_info = (
            (await api.async_get("/Device/DeviceInfo"))
            .get("Device", {})
            .get(
                "DeviceInfo",
                {},
            )
        )
    finally:
        await api.async_close()

    if not isinstance(device_info, dict) or not device_info:
        raise DmNaxApiError("DM NAX did not return device information")

    unique_id = str(
        device_info.get("DeviceId")
        or device_info.get("SerialNumber")
        or data[CONF_HOST].strip().lower()
    )
    title = str(device_info.get("Name") or device_info.get("Model") or DEFAULT_NAME)
    return {"unique_id": unique_id, "title": title}
