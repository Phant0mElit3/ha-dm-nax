"""Test zone renaming against HA registration and actual API payload builders."""

from datetime import timedelta
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.dm_nax import media_player, text
from custom_components.dm_nax.api import DmNaxApi
from custom_components.dm_nax.const import DOMAIN, PLATFORMS
from custom_components.dm_nax.coordinator import DmNaxCoordinator, _normalize_zone


@pytest_asyncio.fixture
async def zone_name(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    platforms = []
    try:
        assert await async_load_base_functionality(hass)
        api = DmNaxApi(Mock(), "example.invalid", "test", "test")
        api._request = AsyncMock(return_value={"Actions": [{"Results": [{"StatusId": 0}]}]})
        coordinator = DmNaxCoordinator(hass, api, scan_interval=None)
        coordinator.async_request_refresh = AsyncMock()
        item = _normalize_zone({"id": "Zone2", "Name": "Office", "ZoneAudio": {"Volume": 300}})
        data = {"device_info": {"DeviceId": "test-nax"}, "output_channels": [item]}
        coordinator.async_set_updated_data(data)
        entry = SimpleNamespace(entry_id="test-entry")
        hass.data[DOMAIN] = {entry.entry_id: coordinator}
        registered = {}
        for module, domain in ((text, "text"), (media_player, "media_player")):
            platform = EntityPlatform(
                hass=hass, logger=logging.getLogger(__name__), domain=domain,
                platform_name=DOMAIN, platform=module,
                scan_interval=timedelta(seconds=30), entity_namespace=None,
            )
            platforms.append(platform)
            entities = []
            await module.async_setup_entry(hass, entry, entities.extend)
            assert len(entities) == 1
            await platform.async_add_entities(entities)
            assert len(platform.entities) == 1
            registered[domain] = entities[0]
        yield SimpleNamespace(hass=hass, api=api, coordinator=coordinator, data=data,
                              entry=entry, text=registered["text"], player=registered["media_player"])
    finally:
        for platform in platforms:
            await platform.async_reset()
        await hass.async_stop()


@pytest.mark.asyncio
async def test_name_control_registration_and_rename(zone_name):
    ctx = zone_name
    assert "text" in PLATFORMS
    entity = ctx.text
    registry = er.async_get(ctx.hass)
    entry = registry.async_get(entity.entity_id)
    assert entry.disabled_by is None
    assert entry.hidden_by is None
    assert entry.entity_category is EntityCategory.CONFIG
    assert entity.native_min == 1
    assert entity.native_max == 50
    assert entity.native_value == "Office"
    text_id, player_id = entity.entity_id, ctx.player.entity_id
    unique_ids = entity.unique_id, ctx.player.unique_id

    await entity.async_set_value("Kitchen")
    ctx.api._request.assert_awaited_once_with(
        "POST", "/Device",
        json_payload={"Device": {"ZoneOutputs": {"Zones": {"Zone2": {"Name": "Kitchen"}}}}},
    )
    ctx.coordinator.async_request_refresh.assert_awaited_once()
    assert entity.native_value == "Office"

    # Only device feedback changes the displayed value and sibling entity name.
    updated = {**ctx.data, "output_channels": [{**ctx.data["output_channels"][0], "Name": "Kitchen"}]}
    ctx.coordinator.async_set_updated_data(updated)
    assert ctx.hass.states.get(text_id).state == "Kitchen"
    assert ctx.player.name == "Kitchen"
    assert (entity.entity_id, ctx.player.entity_id) == (text_id, player_id)
    assert (entity.unique_id, ctx.player.unique_id) == unique_ids
    assert registry.async_get(text_id).id == entry.id


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["", " " * 3, "-Kitchen", "x" * 51, "Kitchen\n", "Kitchen\rOffice"])
async def test_invalid_names_do_not_write(zone_name, value):
    with pytest.raises(ServiceValidationError):
        await zone_name.text.async_set_value(value)
    zone_name.api._request.assert_not_awaited()
    zone_name.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["A", "x" * 50, "Living Room", "Kitchen-Dining", "Caf\u00e9"])
async def test_valid_names(zone_name, value):
    await zone_name.text.async_set_value(value)
    payload = zone_name.api._request.call_args.kwargs["json_payload"]
    assert payload["Device"]["ZoneOutputs"]["Zones"]["Zone2"] == {"Name": value}


@pytest.mark.asyncio
@pytest.mark.parametrize("status_id", [-1, 3])
async def test_rejected_rename_keeps_reported_name(zone_name, status_id):
    zone_name.api._request.return_value = {
        "Actions": [{"Results": [{"StatusId": status_id, "StatusInfo": "Rejected name"}]}]
    }
    with pytest.raises(HomeAssistantError, match="zone rename failed"):
        await zone_name.text.async_set_value("Kitchen")
    assert zone_name.text.native_value == "Office"
    zone_name.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_timeout_keeps_reported_name(zone_name):
    zone_name.api._request.side_effect = TimeoutError()
    with pytest.raises(HomeAssistantError, match="zone rename failed"):
        await zone_name.text.async_set_value("Kitchen")
    assert zone_name.text.native_value == "Office"
    zone_name.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_fallback_does_not_get_zone_writer(zone_name):
    zone_name.coordinator.async_set_updated_data({
        **zone_name.data, "output_channels": [{"id": "Ch001", "Name": "Channel"}],
    })
    entities = []
    await text.async_setup_entry(zone_name.hass, zone_name.entry, entities.extend)
    assert entities == []
