"""AES67 discovery, scoped commands, readback and HA entity registration."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.dm_nax import select
from custom_components.dm_nax.aes67 import (
    receiver_for_output,
    stream_endpoint,
    stream_options,
)
from custom_components.dm_nax.api import DmNaxApi, DmNaxApiError
from custom_components.dm_nax.coordinator import DmNaxCoordinator


def stream(name="Encoder", address="239.69.128.3", port=5004, **values):
    return {
        "SessionNameStatus": name,
        "NetworkAddressStatus": address,
        "PortStatus": port,
        "StreamStatus": "Stream Started",
        **values,
    }


def rx_payload(value):
    return {"Device": {"NaxAudio": {"NaxRx": {"NaxRxStreams": {"Stream07": value}}}}}


@pytest_asyncio.fixture
async def ctx(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    assert await async_load_base_functionality(hass)
    api = DmNaxApi(Mock(), "example.invalid", "user", "secret")
    api.async_post_device = AsyncMock(return_value={})
    api.async_get = AsyncMock(return_value=rx_payload(stream()))
    coordinator = DmNaxCoordinator(hass, api, scan_interval=None)
    coordinator.async_request_refresh = AsyncMock()
    item = {
        "id": "Zone2",
        "Name": "Living Room",
        "NaxRxStream": "Stream07",
        "IsZoneIndependent": True,
        "Volume": 250,
        "IsMuted": True,
    }
    coordinator.async_set_updated_data(
        {
            "device_info": {"DeviceId": "test-nax"},
            "output_channels": [item],
            "nax_rx_streams": {"Stream07": stream()},
            "nax_sdp_streams": {"sdp-key": stream()},
        }
    )
    entry = SimpleNamespace(entry_id="test", async_on_unload=Mock())
    hass.data["dm_nax"] = {entry.entry_id: coordinator}
    try:
        yield SimpleNamespace(
            hass=hass, api=api, coordinator=coordinator, item=item, entry=entry
        )
    finally:
        await coordinator.async_shutdown()
        await hass.async_stop()


def test_options_disambiguate_names_and_reject_invalid_endpoints():
    options = stream_options(
        {
            "a": stream(),
            "b": stream(),
            "off": stream("Off"),
            "bad": stream(address="192.0.2.1"),
        }
    )
    assert options == {
        "Off": None,
        "Encoder (a)": "a",
        "Encoder (b)": "b",
        "Off (off)": "off",
    }


@pytest.mark.parametrize(
    "address,port",
    [("192.0.2.1", 5004), ("bad", 5004), ("239.0.0.1", True), ("239.0.0.1", 65536)],
)
def test_invalid_endpoint(address, port):
    assert stream_endpoint(stream(address=address, port=port)) is None


def test_explicit_receiver_mapping_not_zone_number():
    assert (
        receiver_for_output(
            {"id": "Zone2", "NaxRxStream": "Stream07"}, {"Stream07": {}}
        )
        == "Stream07"
    )
    assert receiver_for_output({"id": "Zone2"}, {"Stream02": {}}) is None
    assert (
        receiver_for_output(
            {"NaxRxStream": "Stream07", "IsZoneIndependent": False}, {"Stream07": {}}
        )
        is None
    )


@pytest.mark.asyncio
async def test_selection_writes_only_mapped_receive_stream(ctx):
    entity = select.DmNaxAes67StreamSelect(ctx.coordinator, ctx.item)
    await entity.async_select_option("Encoder")
    ctx.api.async_post_device.assert_awaited_once_with(
        {
            "Device": {
                "NaxAudio": {
                    "NaxRx": {
                        "NaxRxStreams": {
                            "Stream07": {
                                "SessionNameRequested": "Encoder",
                                "NetworkAddressRequested": "239.69.128.3",
                                "PortRequested": 5004,
                                "IsDisabled": False,
                                "StartRequested": True,
                            }
                        }
                    }
                }
            }
        }
    )
    assert ctx.item["Volume"] == 250 and ctx.item["IsMuted"] is True
    ctx.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_off_stops_only_receiver_and_verifies(ctx):
    ctx.api.async_get.return_value = rx_payload(stream(StreamStatus="Stopped"))
    await select.DmNaxAes67StreamSelect(ctx.coordinator, ctx.item).async_select_option(
        "Off"
    )
    ctx.api.async_post_device.assert_awaited_once_with(
        {
            "Device": {
                "NaxAudio": {
                    "NaxRx": {
                        "NaxRxStreams": {
                            "Stream07": {"StopRequested": True, "IsDisabled": True}
                        }
                    }
                }
            }
        }
    )


@pytest.mark.asyncio
async def test_requested_endpoint_without_actual_reception_is_failure(ctx):
    ctx.api.async_get.return_value = rx_payload(
        stream(address="239.0.0.99", NetworkAddressRequested="239.69.128.3")
    )
    with (
        patch("custom_components.dm_nax.api.asyncio.sleep", new=AsyncMock()),
        pytest.raises(HomeAssistantError, match="did not confirm"),
    ):
        await select.DmNaxAes67StreamSelect(
            ctx.coordinator, ctx.item
        ).async_select_option("Encoder")
    assert ctx.api.async_get.await_count == 20
    ctx.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_delayed_reception_settles(ctx):
    ctx.api.async_get.side_effect = [
        rx_payload(stream(StreamStatus="Connecting")),
        rx_payload(stream()),
    ]
    with patch("custom_components.dm_nax.api.asyncio.sleep", new=AsyncMock()):
        await ctx.api.async_select_aes67_stream("Stream07", stream())
    assert ctx.api.async_get.await_count == 2


@pytest.mark.asyncio
async def test_failed_write_refreshes_and_surfaces_error(ctx):
    ctx.api.async_post_device.side_effect = DmNaxApiError("Rejected")
    with pytest.raises(HomeAssistantError, match="Rejected"):
        await select.DmNaxAes67StreamSelect(
            ctx.coordinator, ctx.item
        ).async_select_option("Encoder")
    ctx.api.async_get.assert_not_called()
    ctx.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_unmapped_or_stale_selection_cannot_write(ctx):
    entity = select.DmNaxAes67StreamSelect(ctx.coordinator, ctx.item)
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("Missing")
    ctx.item["NaxRxStream"] = "Missing"
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("Encoder")
    ctx.api.async_post_device.assert_not_called()


@pytest.mark.asyncio
async def test_feedback_uses_receive_status_and_port(ctx):
    entity = select.DmNaxAes67StreamSelect(ctx.coordinator, ctx.item)
    assert entity.current_option == "Encoder"
    rx = ctx.coordinator.data["nax_rx_streams"]["Stream07"]
    rx["PortStatus"] = 5006
    assert entity.current_option is None
    rx.update(PortStatus=5004, StreamStatus="Connecting")
    assert entity.current_option is None
    rx["StreamStatus"] = "Stream Stopped"
    assert entity.current_option == "Off"


@pytest.mark.asyncio
async def test_receiver_discovery_registers_once_and_preserves_id_on_rename(ctx):
    ctx.item.pop("NaxRxStream")
    entities = []
    await select.async_setup_entry(ctx.hass, ctx.entry, entities.extend)
    assert entities == []
    ctx.item["NaxRxStream"] = "Stream07"
    ctx.coordinator.async_set_updated_data(dict(ctx.coordinator.data))
    assert len(entities) == 1
    entity = entities[0]
    uid = entity.unique_id
    ctx.item["Name"] = "Renamed"
    ctx.coordinator.async_set_updated_data(dict(ctx.coordinator.data))
    assert len(entities) == 1 and entity.unique_id == uid
    assert entity.name == "Renamed AES67 Stream"
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
        assert ctx.hass.states.get(entity.entity_id).state == "Encoder"
    finally:
        await platform.async_reset()


@pytest.mark.asyncio
async def test_coordinator_exposes_discovery_and_receiver_objects(ctx):
    ctx.api.async_get_inventory = AsyncMock(
        return_value={
            "nax_audio": {
                "Device": {
                    "NaxAudio": {
                        "NaxRx": {"NaxRxStreams": {"Stream07": stream()}},
                        "NaxSdp": {"NaxSdpStreams": {"sdp-key": stream()}},
                    }
                }
            }
        }
    )
    data = await ctx.coordinator._async_update_data()
    assert data["nax_rx_streams"]["Stream07"] == stream()
    assert data["nax_sdp_streams"]["sdp-key"] == stream()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", " ", "x" * 32, "-Invalid", "Line\nBreak"])
async def test_invalid_session_names_are_not_offered_or_written(ctx, name):
    assert stream_options({"bad": stream(name)}) == {"Off": None}
    with pytest.raises(DmNaxApiError, match="session name"):
        await ctx.api.async_select_aes67_stream("Stream07", stream(name))
    ctx.api.async_post_device.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_releases_receiver_lock(ctx):
    ctx.api.async_get.side_effect = TimeoutError()
    with pytest.raises(DmNaxApiError, match="Timed out"):
        await ctx.api.async_select_aes67_stream("Stream07", stream())
    assert not ctx.api._rx_locks["Stream07"].locked()


@pytest.mark.asyncio
async def test_missing_readback_is_failure(ctx):
    ctx.api.async_get.return_value = {"Device": {}}
    with pytest.raises(DmNaxApiError, match="Missing AES67"):
        await ctx.api.async_select_aes67_stream("Stream07", stream())


@pytest.mark.asyncio
async def test_inventory_probes_optional_nax_audio(ctx):
    ctx.api._async_optional_object = AsyncMock(return_value={})
    inventory = await ctx.api.async_get_inventory()
    assert "nax_audio" in inventory
    assert "nax_audio" in [
        call.args[0] for call in ctx.api._async_optional_object.call_args_list
    ]
