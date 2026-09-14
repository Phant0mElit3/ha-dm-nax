"""Aliases, telemetry, chime scoping and ducker capability regressions."""

import json
import logging
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import EntityPlatform
from test_aes67 import stream

from custom_components.dm_nax import (
    binary_sensor,
    button,
    config_flow,
    diagnostics,
    number,
    sensor,
    switch,
)
from custom_components.dm_nax.aes67 import stream_options
from custom_components.dm_nax.api import DmNaxApiError, DmNaxUnsupportedObjectError
from custom_components.dm_nax.ducker import (
    GAIN,
    NUMBERS,
    DmNaxDuckerNumber,
    DmNaxDuckerSwitch,
)


def test_options_help_translation_and_alias_example():
    integration = Path(config_flow.__file__).parent
    strings = json.loads((integration / "strings.json").read_text())
    english = json.loads((integration / "translations/en.json").read_text())
    assert strings == english
    description = english["options"]["step"]["init"]["description"]
    assert "https://" not in description
    rendered = description.format(**config_flow._OPTIONS_DESCRIPTION_PLACEHOLDERS)
    assert "MEDIA_AND_AUTOMATION.md#optional-media-player-2" in rendered
    example = description.partition("```yaml\n")[2].partition("```")[0]
    aliases = yaml.safe_load(example)
    assert isinstance(aliases, dict) and len(aliases) == 2
    discovered = {
        str(index): stream(SourceNetworkAddress=address)
        for index, address in enumerate(aliases)
    }
    labels = stream_options(discovered, aliases)
    for index, (address, name) in enumerate(aliases.items()):
        assert config_flow._alias(name) == name
        assert labels[f"{name} [{address}]"] == str(index)


def test_aliases_preserve_discovery_id_and_address():
    discovered = {"abc": stream(SourceNetworkAddress="192.0.2.10")}
    assert stream_options(discovered, {"192.0.2.10": "Apple TV"}) == {
        "Off": None,
        "Apple TV [192.0.2.10]": "abc",
    }
    assert discovered["abc"]["SessionNameStatus"] == "Encoder"


@pytest.mark.asyncio
async def test_option_validation_preserves_unrelated_settings_and_secret(ctx):
    ctx.entry.options = {"media_client_secret": "preserve", "other": 123}
    ctx.entry.data = {"scan_interval": 10}
    flow = config_flow.DmNaxOptionsFlow()
    flow.hass, flow.handler = ctx.hass, ctx.entry.entry_id
    with patch.object(
        ctx.hass.config_entries, "async_get_known_entry", return_value=ctx.entry
    ):
        initial = await flow.async_step_init()
        assert initial["description_placeholders"] == (
            config_flow._OPTIONS_DESCRIPTION_PLACEHOLDERS
        )
        result = await flow.async_step_init({"stream_aliases": {"192.0.2.10": " TV "}})
        assert result["data"]["stream_aliases"] == {"192.0.2.10": "TV"}
        assert result["data"]["media_client_secret"] == "preserve"
        assert result["data"]["other"] == 123
        for bad in (
            {"invalid": "TV"},
            {"192.0.2.10": ""},
            {"192.0.2.10": "bad\nname"},
            [],
        ):
            result = await flow.async_step_init({"stream_aliases": bad})
            assert result["errors"]["base"] == "invalid_aliases"
            assert result["description_placeholders"] == initial["description_placeholders"]
        result = await flow.async_step_init({"enable_media_player": True})
        assert result["errors"]["base"] == "invalid_media_credentials"
        assert result["description_placeholders"] == initial["description_placeholders"]


@pytest.mark.asyncio
async def test_diagnostics_never_include_config_or_private_payloads(ctx):
    ctx.entry.data = {"password": "SECRET"}
    ctx.entry.options = {"media_client_secret": "MP2-SECRET"}
    ctx.coordinator.data["device"] = {"SessionToken": "TOKEN"}
    ctx.coordinator.data["device_info"]["SerialNumber"] = "PRIVATE-SERIAL"
    result = json.dumps(
        await diagnostics.async_get_config_entry_diagnostics(ctx.hass, ctx.entry)
    )
    for value in ("SECRET", "TOKEN", "PRIVATE-SERIAL", "Living Room", "239.69"):
        assert value not in result


@pytest.mark.asyncio
async def test_real_sensor_and_button_registration(ctx):
    ctx.item.update(IsSignalDetected=True, IsSignalClipping=False)
    ctx.coordinator.data["door_chimes"] = {
        "CustomChimes": {
            "CustomSlot1": {
                "Name": "Announcement",
                "PlaybackInProgress": False,
                "PlaybackZones": {"Zone2": {"IsEnabled": True}},
            }
        }
    }
    for module, domain in (
        (sensor, "sensor"),
        (binary_sensor, "binary_sensor"),
        (button, "button"),
    ):
        platform = EntityPlatform(
            hass=ctx.hass,
            logger=logging.getLogger(__name__),
            domain=domain,
            platform_name="dm_nax",
            platform=module,
            scan_interval=timedelta(seconds=30),
            entity_namespace=None,
        )
        entities = []
        await module.async_setup_entry(ctx.hass, ctx.entry, entities.extend)
        assert entities
        try:
            await platform.async_add_entities(entities)
            for entity in entities:
                state = ctx.hass.states.get(entity.entity_id)
                assert state is not None
                assert state.state != "unavailable"
        finally:
            await platform.async_reset()


@pytest.mark.asyncio
async def test_monitors_lose_capability_and_follow_receiver_mapping(ctx):
    entity = sensor.DmNaxSensor(
        ctx.coordinator, ctx.item, "rx", "StreamStatus", "Status", None
    )
    assert entity.native_value == "Stream Started"
    ctx.item["NaxRxStream"] = "other"
    assert not entity.available and entity.native_value is None
    ctx.coordinator.data["nax_rx_streams"]["other"] = {"StreamStatus": "Connecting"}
    assert entity.available and entity.native_value == "Connecting"


@pytest.mark.asyncio
async def test_chime_writes_only_play_and_never_routes_or_unmutes(ctx):
    chime = {
        "Name": "Bell",
        "PlaybackInProgress": False,
        "PlaybackZones": {"Zone2": {"IsEnabled": True}},
    }
    ctx.api.async_get.return_value = {
        "Device": {"DoorChimes": {"DefaultChimes": {"DefaultSlot1": chime}}}
    }
    await ctx.api.async_play_chime("DefaultChimes", "DefaultSlot1")
    ctx.api.async_post_device.assert_awaited_once_with(
        {"Device": {"DoorChimes": {"DefaultChimes": {"DefaultSlot1": {"Play": True}}}}}
    )
    assert chime["PlaybackZones"] == {"Zone2": {"IsEnabled": True}}
    assert ctx.item["Volume"] == 250 and ctx.item["IsMuted"]
    chime["PlaybackInProgress"] = True
    with pytest.raises(DmNaxApiError, match="already playing"):
        await ctx.api.async_play_chime("DefaultChimes", "DefaultSlot1")
    ctx.api.async_post_device.assert_awaited_once()


@pytest.mark.asyncio
async def test_chime_missing_and_invalid_references_never_write(ctx):
    for collection, key in (
        ("evil", "DefaultSlot1"),
        ("CustomChimes", "../bad"),
        ("DefaultChimes", "missing"),
    ):
        with pytest.raises(DmNaxApiError):
            await ctx.api.async_play_chime(collection, key)
    ctx.api.async_post_device.assert_not_awaited()


@pytest.mark.asyncio
async def test_ducker_units_validation_scoping_and_capability_loss(ctx):
    ctx.coordinator.data["ducker_outputs"] = {
        "Output007": {
            "AttackTime": 10,
            "DuckerInputs": {"Input003": {"GainLevel": -200}},
        }
    }
    entity = DmNaxDuckerNumber(
        ctx.coordinator, "Output007", ("AttackTime",), NUMBERS[0]
    )
    assert entity.native_value == 1
    await entity.async_set_native_value(1.5)
    ctx.api.async_post_device.assert_awaited_with(
        {
            "Device": {
                "DuckerConfig": {"DuckerOutputs": {"Output007": {"AttackTime": 15}}}
            }
        }
    )
    for value in (float("nan"), float("inf"), 0, 2001):
        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(value)
    gain = DmNaxDuckerNumber(
        ctx.coordinator, "Output007", ("DuckerInputs", "Input003", "GainLevel"), GAIN
    )
    assert gain.native_value == -20
    await gain.async_set_native_value(-25)
    ctx.api.async_post_device.assert_awaited_with(
        {
            "Device": {
                "DuckerConfig": {
                    "DuckerOutputs": {
                        "Output007": {"DuckerInputs": {"Input003": {"GainLevel": -250}}}
                    }
                }
            }
        }
    )
    del ctx.coordinator.data["ducker_outputs"]["Output007"]["AttackTime"]
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await entity.async_set_native_value(1)


@pytest.mark.asyncio
async def test_ducker_discovery_and_rejected_command_preserves_feedback(ctx):
    ctx.coordinator.data["ducker_outputs"] = {
        "Output003": {"IsBypassEnabled": False, "Threshold": -30}
    }
    for module in (number, switch):
        entities = []
        await module.async_setup_entry(ctx.hass, ctx.entry, entities.extend)
        assert len(entities) == 1
        assert entities[0].entity_registry_enabled_default is False
    entity = DmNaxDuckerSwitch(
        ctx.coordinator, "Output003", ("IsBypassEnabled",), "Bypass"
    )
    ctx.api.async_post_device.side_effect = DmNaxApiError("rejected")
    with pytest.raises(HomeAssistantError, match="rejected"):
        await entity.async_turn_on()
    assert entity.is_on is False


@pytest.mark.asyncio
async def test_optional_objects_only_suppress_unsupported(ctx):
    ctx.api.async_get.side_effect = DmNaxUnsupportedObjectError()
    assert await ctx.api._async_optional_object("ducker_config") == {}
    ctx.api.async_get.side_effect = DmNaxApiError("transport")
    with pytest.raises(DmNaxApiError):
        await ctx.api._async_optional_object("door_chimes")


def test_fault_sensor_uses_speaker_faults_not_zone_root(ctx):
    ctx.item["Speaker"] = {"Faults": {"IsCriticalFaultDetected": True}}
    entity = binary_sensor.DmNaxBinarySensor(
        ctx.coordinator,
        ctx.item,
        "fault",
        "IsCriticalFaultDetected",
        "Critical Fault",
        None,
    )
    assert entity.is_on is True
    del ctx.item["Speaker"]["Faults"]["IsCriticalFaultDetected"]
    assert entity.is_on is None and not entity.available
