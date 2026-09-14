"""Visible source selection and compatibility with existing zone controls."""

import logging
from copy import deepcopy
from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.dm_nax import select
from custom_components.dm_nax.api import DmNaxApiError
from custom_components.dm_nax.media_player import DmNaxOutputChannel


def configure_sources(ctx):
    inputs = [
        {"id": "Input1", "Name": "Turntable"},
        {"id": "Input5", "Name": "Digital TV"},
        {"id": "Input9", "Name": "Media Player 1"},
        {"id": "AES67", "Name": "AES67"},
    ]
    ctx.coordinator.data["input_channels"] = inputs
    ctx.coordinator.data["inputs_by_source_id"] = {item["id"]: item for item in inputs}
    ctx.coordinator.data["inputs_by_source_id"]["Ch001"] = inputs[0]
    ctx.item.update(route_id="Output2", source_id="Input1")
    return inputs


@pytest.mark.asyncio
async def test_source_select_registers_next_to_existing_aes67_select(ctx):
    configure_sources(ctx)
    entities = []
    await select.async_setup_entry(ctx.hass, ctx.entry, entities.extend)
    source = next(
        item for item in entities if isinstance(item, select.DmNaxSourceSelect)
    )
    aes67 = next(
        item for item in entities if isinstance(item, select.DmNaxAes67StreamSelect)
    )
    assert source.unique_id == "dm_nax_test-nax_Zone2_source"
    assert aes67.unique_id == "dm_nax_test-nax_Zone2_aes67_stream"
    ctx.api.async_post_device.assert_not_called()
    platform = EntityPlatform(
        hass=ctx.hass,
        logger=logging.getLogger(__name__),
        domain="select",
        platform_name="dm_nax",
        platform=select,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    try:
        await platform.async_add_entities(entities)
        state = ctx.hass.states.get(source.entity_id)
        assert state.state == "Turntable"
        assert state.attributes["options"] == [
            "Turntable",
            "Digital TV",
            "Media Player 1",
            "AES67",
        ]
        assert source.entity_registry_enabled_default
    finally:
        await platform.async_reset()


@pytest.mark.asyncio
@pytest.mark.parametrize("source_id", ["Input1", "Input5", "Input9", "AES67"])
async def test_select_matches_media_player_and_writes_only_matrix_route(ctx, source_id):
    inputs = configure_sources(ctx)
    before = deepcopy(ctx.coordinator.data)
    entity = select.DmNaxSourceSelect(ctx.coordinator, ctx.item)
    player = DmNaxOutputChannel(ctx.coordinator, ctx.item)
    assert entity.options == player.source_list
    option = next(item["Name"] for item in inputs if item["id"] == source_id)
    await entity.async_select_option(option)
    ctx.api.async_post_device.assert_awaited_once_with(
        {
            "Device": {
                "AvMatrixRouting": {"Routes": {"Output2": {"AudioSource": source_id}}}
            }
        }
    )
    ctx.coordinator.async_request_refresh.assert_awaited_once()
    assert ctx.coordinator.data == before
    assert entity.current_option == "Turntable"
    ctx.item["source_id"] = source_id
    assert entity.current_option == player.source == option
    ctx.api.async_post_device.reset_mock()
    await player.async_select_source(option)
    ctx.api.async_post_device.assert_awaited_once_with(
        {
            "Device": {
                "AvMatrixRouting": {"Routes": {"Output2": {"AudioSource": source_id}}}
            }
        }
    )


@pytest.mark.asyncio
async def test_source_failure_refreshes_without_optimistic_selection(ctx):
    configure_sources(ctx)
    entity = select.DmNaxSourceSelect(ctx.coordinator, ctx.item)
    ctx.api.async_post_device.side_effect = DmNaxApiError("Rejected")
    with pytest.raises(HomeAssistantError, match="Rejected"):
        await entity.async_select_option("Digital TV")
    assert entity.current_option == "Turntable"
    ctx.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_routes_unknown_options_and_unavailable_device_cannot_write(ctx):
    configure_sources(ctx)
    entity = select.DmNaxSourceSelect(ctx.coordinator, ctx.item)
    with pytest.raises(HomeAssistantError, match="Unknown"):
        await entity.async_select_option("Analog Output 4")
    ctx.item.pop("route_id")
    assert not entity.available
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await entity.async_select_option("Turntable")
    ctx.item["route_id"] = "Output2"
    ctx.coordinator.last_update_success = False
    assert not entity.available
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await entity.async_select_option("Turntable")
    ctx.api.async_post_device.assert_not_called()


@pytest.mark.asyncio
async def test_source_names_update_and_duplicate_labels_remain_distinct(ctx):
    inputs = configure_sources(ctx)
    inputs[0]["Name"] = inputs[1]["Name"] = "TV"
    inputs[2]["Name"] = "TV (Input1)"
    entity = select.DmNaxSourceSelect(ctx.coordinator, ctx.item)
    player = DmNaxOutputChannel(ctx.coordinator, ctx.item)
    assert len(set(entity.options)) == len(inputs)
    assert entity.options == player.source_list
    for item, option in zip(inputs, entity.options, strict=True):
        ctx.item["source_id"] = item["id"]
        assert entity.current_option == player.source == option
    ctx.item["source_id"] = "Ch001"
    assert entity.current_option == entity.options[0]
    uid = entity.unique_id
    ctx.item["Name"] = "Renamed Room"
    inputs[0]["Name"] = "Record Player"
    assert entity.name == "Renamed Room Source"
    assert entity.current_option == "Record Player"
    assert entity.unique_id == uid
    ctx.item["source_id"] = "Record Player"
    assert entity.current_option is None
    ctx.item.pop("source_id")
    assert entity.current_option is None
    ctx.coordinator.data["input_channels"] = []
    assert not entity.available


@pytest.mark.asyncio
async def test_source_discovery_handles_late_routes_without_duplicates(ctx):
    ctx.item.pop("NaxRxStream")
    entities = []
    await select.async_setup_entry(ctx.hass, ctx.entry, entities.extend)
    assert entities == []
    configure_sources(ctx)
    ctx.coordinator.async_set_updated_data(dict(ctx.coordinator.data))
    assert len(entities) == 1
    assert isinstance(entities[0], select.DmNaxSourceSelect)
    ctx.coordinator.async_set_updated_data(dict(ctx.coordinator.data))
    assert len(entities) == 1
