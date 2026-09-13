"""Crestron DM NAX integration."""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from yarl import URL

from .api import DmNaxApi
from .const import (
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import DmNaxCoordinator
from .media import DmNaxMedia

_LOGGER = logging.getLogger(__name__)

_COMMON_ZONE_CONTROL_SUFFIXES = frozenset(
    {
        "lineoutvolume",
        "bass",
        "treble",
        "balance",
        "delayinms",
        "substrimlevel",
        "isloudnessenabled",
        "isdndenabled",
        "iseqbypassenabled",
        "islineouteqbypassenabled",
        "isduckingenabled",
        "isstereoenabled",
        "iscssenabled",
        "toneprofile",
        "nightmode",
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DM NAX from a config entry."""
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    if isinstance(scan_interval, int):
        scan_interval = timedelta(seconds=max(5, min(300, scan_interval)))

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
    coordinator.stream_aliases = entry.options.get("stream_aliases", {})
    if entry.options.get("enable_media_player") and entry.data.get(CONF_USE_SSL, True):
        api.include_media = True
        coordinator.media = DmNaxMedia(
            session,
            str(URL(api.base_url).with_scheme("wss").with_path("/subscriptionmgr")),
            entry.options.get("media_client_id", ""),
            entry.options.get("media_client_secret", ""),
            verify_ssl,
            coordinator.async_update_listeners,
        )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.async_close_media()
        await api.async_close()
        raise

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    try:
        await hass.config_entries.async_forward_entry_setups(
            entry,
            [Platform(platform) for platform in PLATFORMS],
        )
    except Exception:
        await coordinator.async_close_media()
        await api.async_close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    entry.async_on_unload(entry.add_update_listener(_async_reload_options))
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
        await coordinator.async_close_media()
        await coordinator.api.async_close()
    return unload_ok


def _async_enable_common_zone_controls(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Enable common zone controls that older versions registered as disabled."""
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.domain not in {"number", "select", "switch"}:
            continue
        if registry_entry.disabled_by != er.RegistryEntryDisabler.INTEGRATION:
            continue
        match = re.fullmatch(
            r"dm_nax_.+_(?:Zone[0-9]+|Ch[0-9]+)_([a-z]+)", registry_entry.unique_id
        )
        if not match or match[1] not in _COMMON_ZONE_CONTROL_SUFFIXES:
            continue
        registry.async_update_entity(registry_entry.entity_id, disabled_by=None)


async def _async_reload_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply polling changes immediately."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Apply the common-control migration once, preserving later user choices."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        _async_enable_common_zone_controls(hass, entry)
        hass.config_entries.async_update_entry(entry, minor_version=2)
    return True
