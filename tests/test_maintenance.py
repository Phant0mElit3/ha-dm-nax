"""Regression coverage for the API and HA maintenance audit."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from aiohttp import ClientConnectionError, ClientSession, TCPConnector
from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dm_nax import (
    _async_enable_common_zone_controls,
    _async_reload_options,
    async_migrate_entry,
    config_flow,
    number,
    select,
)
from custom_components.dm_nax.api import (
    DmNaxApi,
    DmNaxApiError,
    DmNaxAuthError,
    DmNaxUnsupportedObjectError,
    _raise_for_action_results,
)
from custom_components.dm_nax.controls import description_supported
from custom_components.dm_nax.coordinator import DmNaxCoordinator
from custom_components.dm_nax.media_player import DmNaxOutputChannel


@pytest_asyncio.fixture
async def ctx(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    assert await async_load_base_functionality(hass)
    api = DmNaxApi(Mock(), "example.invalid", "test", "test")
    api._request = AsyncMock(return_value={})
    coordinator = DmNaxCoordinator(hass, api, scan_interval=None)
    coordinator.async_request_refresh = AsyncMock()
    item = {"id": "Zone2", "Name": "Office", "Volume": 300, "route_id": "Output2"}
    coordinator.async_set_updated_data(
        {
            "device_info": {"DeviceId": "test-nax"},
            "output_channels": [item],
            "input_channels": [],
        }
    )
    entry = SimpleNamespace(entry_id="test", async_on_unload=Mock())
    try:
        yield SimpleNamespace(
            hass=hass, api=api, coordinator=coordinator, item=item, entry=entry
        )
    finally:
        await coordinator.async_shutdown()
        await hass.async_stop()


def response(status=200, payload=None, headers=None):
    result = AsyncMock()
    result.status = status
    result.headers = headers or {}
    result.content_length = 1
    result.json.return_value = payload or {"Device": {}}
    result.__aenter__.return_value = result
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ClientConnectionError("offline"), TimeoutError()])
async def test_login_connection_failure_is_not_bad_password(error):
    session = Mock(get=AsyncMock(side_effect=error))
    api = DmNaxApi(session, "example.invalid", "user", "password")
    with pytest.raises(DmNaxApiError) as raised:
        await api.async_login()
    assert not isinstance(raised.value, DmNaxAuthError)
    assert session.get.call_args.kwargs["timeout"].total == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["request", "body"])
async def test_request_and_body_timeouts_are_wrapped(phase):
    reply = response()
    if phase == "body":
        reply.json.side_effect = TimeoutError()
    session = Mock(
        request=AsyncMock(
            side_effect=TimeoutError() if phase == "request" else None,
            return_value=reply,
        )
    )
    api = DmNaxApi(session, "example.invalid", "user", "password")
    api._authenticated = True
    with pytest.raises(DmNaxApiError, match="timed out"):
        await api.async_get("/Device")
    assert session.request.call_args.kwargs["timeout"].connect == 5


@pytest.mark.asyncio
async def test_expired_session_reauth_and_token_rotation_are_serialized():
    session = Mock(
        get=AsyncMock(return_value=response()),
        post=AsyncMock(return_value=response(headers={"CREST-XSRF-TOKEN": "fresh"})),
        request=AsyncMock(
            side_effect=[
                response(403),
                response(headers={"CREST-XSRF-TOKEN": "rotated"}),
                response(),
            ]
        ),
    )
    api = DmNaxApi(session, "example.invalid", "user", "password")
    api._authenticated, api._xsrf_token = True, "expired"
    await asyncio.gather(
        api.async_set_output_mute("Zone1", True),
        api.async_set_output_mute("Zone2", True),
    )
    tokens = [
        call.kwargs["headers"]["X-CREST-XSRF-TOKEN"]
        for call in session.request.call_args_list
    ]
    assert tokens == ["expired", "fresh", "rotated"]
    session.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_second_rejection_starts_auth_repair():
    session = Mock(request=AsyncMock(return_value=response(403)))
    api = DmNaxApi(session, "example.invalid", "user", "password")
    api._authenticated = True

    async def login():
        api._authenticated = True

    api._async_login = AsyncMock(side_effect=login)
    with pytest.raises(DmNaxAuthError):
        await api.async_get("/Device")
    assert session.request.await_count == 2
    assert not api._authenticated


@pytest.mark.asyncio
async def test_managed_session_detach_preserves_shared_connector():
    connector = TCPConnector()
    session = ClientSession(connector=connector, connector_owner=False)
    other = ClientSession(connector=connector, connector_owner=False)
    try:
        api = DmNaxApi(session, "example.invalid", "u", "p")
        await api.async_close()
        assert session.closed
        assert not other.closed and not connector.closed
    finally:
        await other.close()
        await connector.close()


@pytest.mark.asyncio
async def test_owned_session_closes():
    async with ClientSession() as session:
        await DmNaxApi(
            session, "example.invalid", "u", "p", owns_session=True
        ).async_close()
        assert session.closed


@pytest.mark.parametrize("status", [-1, 1, 2, 3, 4])
def test_nonzero_action_results_are_not_silent_success(status):
    with pytest.raises(DmNaxApiError):
        _raise_for_action_results({"Actions": [{"Results": [{"StatusId": status}]}]})


@pytest.mark.asyncio
async def test_inventory_uses_channel_fallback(ctx):
    async def read(path):
        if path.endswith(
            ("InputSources", "ZoneOutputs", "AudioRanges", "AvMatrixRouting")
        ):
            raise DmNaxUnsupportedObjectError()
        name = path.rsplit("/", 1)[1]
        if name == "DeviceInfo":
            return {"Device": {name: {"DeviceId": "test-nax"}}}
        return {
            "Device": {
                name: {"Channels": {"Ch001": {"Name": "Channel", "Volume": 400}}}
            }
        }

    ctx.api.async_get = AsyncMock(side_effect=read)
    data = await ctx.coordinator._async_update_data()
    assert data["output_channels"][0]["id"] == "Ch001"
    assert data["input_channels"][0]["id"] == "Ch001"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,expected",
    [(DmNaxAuthError(), ConfigEntryAuthFailed), (DmNaxApiError(), UpdateFailed)],
)
async def test_optional_endpoint_failures_are_not_hidden(ctx, error, expected):
    async def read(path):
        if path.endswith("DeviceInfo"):
            return {"Device": {"DeviceInfo": {"DeviceId": "test-nax"}}}
        raise error

    ctx.api.async_get = AsyncMock(side_effect=read)
    with pytest.raises(expected):
        await ctx.coordinator._async_update_data()


@pytest.mark.asyncio
@pytest.mark.parametrize("maximum", [150, 300, 500])
@pytest.mark.parametrize(
    "output_id,object_name", [("Zone2", "Speaker"), ("Ch001", "AmpOutput")]
)
async def test_power_limit_and_object_family(ctx, maximum, output_id, object_name):
    item = {"id": output_id, object_name: {"Power": 50, "PowerMax": maximum}}
    ctx.coordinator.data["output_channels"] = [item]
    desc = next(d for d in number.NUMBER_DESCRIPTIONS if d.key == "SpeakerPower")
    entity = number.DmNaxZoneNumber(ctx.coordinator, item, desc)
    assert entity.available
    assert entity.native_max_value == maximum
    await entity.async_set_native_value(maximum + 100)
    payload = ctx.api._request.call_args.kwargs["json_payload"]["Device"]
    if output_id.startswith("Zone"):
        assert payload["ZoneOutputs"]["Zones"][output_id]["ZoneAudio"] == {
            "Speaker": {"Power": maximum}
        }
    else:
        assert payload["OutputChannels"]["Channels"][output_id] == {
            "AmpOutput": {"Power": maximum}
        }


@pytest.mark.asyncio
async def test_channel_readonly_fields_and_impedance(ctx):
    item = {"id": "Ch001", "MuteVolume": -800, "AmpOutput": {"Impedance": "8ohm"}}
    ctx.coordinator.data["output_channels"] = [item]
    mute = next(d for d in number.NUMBER_DESCRIPTIONS if d.key == "MuteVolume")
    assert not description_supported(item, mute)
    desc = next(d for d in select.SELECT_DESCRIPTIONS if d.key == "SpeakerImpedance")
    entity = select.DmNaxZoneSelect(ctx.coordinator, item, desc)
    assert "NoSpeaker" in entity.options
    await entity.async_select_option("NoSpeaker")
    assert ctx.api._request.call_args.kwargs["json_payload"] == {
        "Device": {
            "OutputChannels": {
                "Channels": {"Ch001": {"AmpOutput": {"Impedance": "NoSpeaker"}}}
            }
        }
    }


@pytest.mark.asyncio
async def test_dynamic_capability_discovery_and_write_guard(ctx):
    ctx.item["Peq"] = {
        "Bands": {"Band01": {"Gain": 0, "GainMax": 120, "IsGainSupported": False}}
    }
    ctx.hass.data["dm_nax"] = {ctx.entry.entry_id: ctx.coordinator}
    entities = []
    await number.async_setup_entry(ctx.hass, ctx.entry, entities.extend)
    assert not entities
    band = ctx.item["Peq"]["Bands"]["Band01"]
    band["IsGainSupported"] = True
    ctx.coordinator.async_set_updated_data(ctx.coordinator.data)
    assert len(entities) == 1
    entity = entities[0]
    assert entity.available and entity.native_max_value == 12
    band["IsGainSupported"] = False
    ctx.coordinator.async_set_updated_data(ctx.coordinator.data)
    assert not entity.available
    with pytest.raises(HomeAssistantError, match="not currently supported"):
        await entity.async_set_native_value(1)
    ctx.api._request.assert_not_awaited()
    band["IsGainSupported"] = True
    ctx.coordinator.async_set_updated_data(ctx.coordinator.data)
    assert len(entities) == 1 and entity.available


def test_crossover_and_bandwidth_capabilities():
    crossover = next(
        d for d in number.NUMBER_DESCRIPTIONS if d.key == "CrossOverFrequencyInHz"
    )
    item = {
        "id": "Zone2",
        "CrossOverFrequencyInHz": 80,
        "IsZoneIndependent": True,
        "ZoneConfiguration": "Standard",
    }
    assert not description_supported(item, crossover)
    item["ZoneConfiguration"] = "Bridged2p1"
    assert description_supported(item, crossover)
    item["IsZoneIndependent"] = False
    assert not description_supported(item, crossover)
    bandwidth = next(
        d for d in number.NUMBER_DESCRIPTIONS if d.key == "Band01Bandwidth"
    )
    assert not description_supported(
        {
            "id": "Ch001",
            "Peq": {
                "Bands": {"Band01": {"Bandwidth": 33, "IsBandwithSupported": False}}
            },
        },
        bandwidth,
    )


@pytest.mark.asyncio
async def test_reported_audio_ranges_control_delay(ctx):
    ctx.item["DelayInms"] = 100
    ctx.coordinator.data["audio_ranges"] = {
        "BasicControls": {
            "DelayInms": {
                "Units": "ms",
                "Scale": "1",
                "Min": 0,
                "Max": 500,
            }
        }
    }
    desc = next(d for d in number.NUMBER_DESCRIPTIONS if d.key == "DelayInms")
    entity = number.DmNaxZoneNumber(ctx.coordinator, ctx.item, desc)
    assert entity.native_max_value == 500 and entity.native_min_value == 0
    await entity.async_set_native_value(400)
    assert ctx.api._request.call_args.kwargs["json_payload"]["Device"]["ZoneOutputs"][
        "Zones"
    ]["Zone2"]["ZoneAudio"] == {"DelayInms": 400}


@pytest.mark.asyncio
async def test_common_migration_does_not_enable_peq_or_user_disabled(ctx):
    registry = er.async_get(ctx.hass)
    disabled = er.RegistryEntryDisabler
    cases = [
        ("Zone2_iseqbypassenabled", disabled.INTEGRATION, None),
        (
            "Zone2_peq_bands_band01_iseqbypassenabled",
            disabled.INTEGRATION,
            disabled.INTEGRATION,
        ),
        ("Zone3_iseqbypassenabled", disabled.USER, disabled.USER),
    ]
    entries = []
    for suffix, old, new in cases:
        record = registry.async_get_or_create(
            "switch",
            "dm_nax",
            f"dm_nax_test-nax_{suffix}",
            disabled_by=old,
        )
        entries.append((record, new))
    with patch(
        "custom_components.dm_nax.er.async_entries_for_config_entry",
        return_value=[r for r, _ in entries],
    ):
        _async_enable_common_zone_controls(ctx.hass, ctx.entry)
    for record, expected in entries:
        assert registry.async_get(record.entity_id).disabled_by is expected
    ctx.entry.version, ctx.entry.minor_version = 1, 2
    with patch(
        "custom_components.dm_nax._async_enable_common_zone_controls"
    ) as migrate:
        assert await async_migrate_entry(ctx.hass, ctx.entry)
        migrate.assert_not_called()


@pytest.mark.asyncio
async def test_options_use_current_ha_property_and_validate_interval(ctx):
    ctx.entry.options, ctx.entry.data = {}, {"scan_interval": 10}
    flow = config_flow.DmNaxConfigFlow.async_get_options_flow(ctx.entry)
    flow.hass, flow.handler = ctx.hass, ctx.entry.entry_id
    with patch.object(
        ctx.hass.config_entries, "async_get_known_entry", return_value=ctx.entry
    ):
        form = await flow.async_step_init()
        for value in (-1, 0, 4, 301):
            with pytest.raises(config_flow.vol.Invalid):
                form["data_schema"]({"scan_interval": value})
        assert form["data_schema"]({"scan_interval": 5})["scan_interval"] == 5
        result = await flow.async_step_init({"scan_interval": 15})
        assert result["data"] == {"scan_interval": 15}
    with patch.object(
        ctx.hass.config_entries, "async_reload", new=AsyncMock()
    ) as reload:
        await _async_reload_options(ctx.hass, ctx.entry)
        reload.assert_awaited_once_with(ctx.entry.entry_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["reauth_confirm", "reconfigure"])
async def test_connection_repair_and_wrong_device_guard(ctx, step):
    entry = ctx.entry
    entry.data = {"host": "example.invalid", "username": "old", "password": "old"}
    entry.unique_id = "test-nax"
    entry.title = "NAX"
    flow = config_flow.DmNaxConfigFlow()
    flow.hass = ctx.hass
    flow.context = {
        "source": "reauth" if step == "reauth_confirm" else "reconfigure",
        "entry_id": entry.entry_id,
    }
    with (
        patch.object(flow, "_get_reauth_entry", return_value=entry),
        patch.object(flow, "_get_reconfigure_entry", return_value=entry),
        patch.object(
            flow, "async_update_reload_and_abort", return_value={"type": "abort"}
        ) as update,
        patch(
            "custom_components.dm_nax.config_flow._async_validate_input",
            new=AsyncMock(return_value={"unique_id": "test-nax", "title": "NAX"}),
        ) as validate,
    ):
        await flow._async_update_connection(
            step, {"username": "new", "password": "new"}
        )
        assert update.call_args.kwargs["data"]["password"] == "new"
        assert update.call_args.kwargs["data"]["host"] == "example.invalid"
        update.reset_mock()
        validate.return_value["unique_id"] = "different-nax"
        from homeassistant.data_entry_flow import AbortFlow

        with pytest.raises(AbortFlow):
            await flow._async_update_connection(
                step, {"username": "new", "password": "new"}
            )
        update.assert_not_called()
        validate.side_effect = DmNaxAuthError()
        result = await flow._async_update_connection(step, {"password": "bad"})
        assert result["errors"] == {"base": "invalid_auth"}
        validate.side_effect = DmNaxApiError()
        result = await flow._async_update_connection(step, {"password": "bad"})
        assert result["errors"] == {"base": "cannot_connect"}


def player(ctx):
    entity = DmNaxOutputChannel(ctx.coordinator, ctx.item)
    entity.hass = ctx.hass
    entity.async_write_ha_state = Mock()
    return entity


@pytest.mark.asyncio
async def test_duplicate_source_names_are_roundtrippable(ctx):
    items = [
        {"id": "Input1", "Name": "TV"},
        {"id": "Input2", "Name": "TV"},
        {"id": "Input3", "Name": "TV (Input1)"},
    ]
    ctx.coordinator.data["input_channels"] = items
    ctx.coordinator.data["inputs_by_source_id"] = {item["id"]: item for item in items}
    entity = player(ctx)
    assert len(set(entity.source_list)) == 3
    for item, label in zip(items, entity.source_list, strict=True):
        ctx.item["source_id"] = item["id"]
        assert entity.source == label
        await entity.async_select_source(label)
        assert ctx.api._request.call_args.kwargs["json_payload"]["Device"][
            "AvMatrixRouting"
        ]["Routes"]["Output2"] == {"AudioSource": item["id"]}


@pytest.mark.asyncio
async def test_volume_bounds_feedback_and_expiry(ctx):
    entity = player(ctx)
    ctx.item.update(MinVolume=100, MaxVolume=800)
    await entity.async_set_volume_level(1)
    assert entity.volume_level == 0.8
    assert ctx.api._request.call_args.kwargs["json_payload"]["Device"]["ZoneOutputs"][
        "Zones"
    ]["Zone2"]["ZoneAudio"] == {"Volume": 800}
    # A genuinely new device value wins immediately, even during settling.
    ctx.item["Volume"] = 450
    entity._handle_coordinator_update()
    assert entity.volume_level == 0.45
    await entity.async_set_volume_level(-1)
    assert entity.volume_level == 0.1
    entity._expire_volume(None)
    assert entity.volume_level == 0.45
    assert entity._cancel_volume_timer is None
    await ctx.hass.async_block_till_done()


@pytest.mark.asyncio
async def test_out_of_order_volume_completion_keeps_latest_command(ctx):
    entity = player(ctx)
    first_started, release_first = asyncio.Event(), asyncio.Event()

    async def volume(output_id, level):
        if level == 400:
            first_started.set()
            await release_first.wait()

    ctx.api.async_set_output_volume = AsyncMock(side_effect=volume)
    first = asyncio.create_task(entity.async_set_volume_level(0.4))
    await first_started.wait()
    await entity.async_set_volume_level(0.6)
    release_first.set()
    await first
    assert entity.volume_level == 0.6
    entity._clear_optimistic_volume()


@pytest.mark.asyncio
async def test_rejected_volume_never_claims_success(ctx):
    entity = player(ctx)
    ctx.api._request.side_effect = DmNaxApiError("rejected")
    with pytest.raises(HomeAssistantError):
        await entity.async_set_volume_level(0.7)
    assert entity.volume_level == 0.3
