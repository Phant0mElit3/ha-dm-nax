"""Crestron DM NAX integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import DmNaxApi
from .const import CONF_USE_SSL, CONF_VERIFY_SSL, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import DmNaxCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DM NAX from a config entry."""
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    if isinstance(scan_interval, int):
        scan_interval = timedelta(seconds=scan_interval)

    verify_ssl = entry.data.get(CONF_VERIFY_SSL, False)
    session = async_create_clientsession(
        hass,
        verify_ssl=verify_ssl,
        cookie_jar=CookieJar(unsafe=True),
    )
    api = DmNaxApi(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        use_ssl=entry.data.get(CONF_USE_SSL, True),
        verify_ssl=verify_ssl,
    )
    coordinator = DmNaxCoordinator(
        hass,
        api,
        scan_interval=scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform(platform) for platform in PLATFORMS],
    )
    _LOGGER.info("DM NAX integration set up for host %s", entry.data[CONF_HOST])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [Platform(platform) for platform in PLATFORMS],
    )
    if unload_ok:
        coordinator: DmNaxCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.async_close()
    return unload_ok

