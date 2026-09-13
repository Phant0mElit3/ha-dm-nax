"""Validate the optional audio-follow blueprint with Home Assistant schemas."""

from pathlib import Path

import pytest
from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import State
from homeassistant.helpers.template import Template
from homeassistant.util.yaml import load_yaml


@pytest.mark.asyncio
async def test_blueprint_schema_and_music_preservation(ctx):
    data = load_yaml(
        str(
            Path(__file__).parents[1]
            / "blueprints/automation/nvx_nax_audio_follow.yaml"
        )
    )
    blueprint = Blueprint(data, schema=BLUEPRINT_SCHEMA, expected_domain="automation")
    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "input": {
                    "enabled": "input_boolean.follow",
                    "video_source": "select.video",
                    "audio_stream": "select.audio",
                    "zone": "media_player.zone",
                    "source_map": {"TV": "192.0.2.10"},
                }
            }
        },
    )
    inputs.validate()
    config = inputs.async_substitute()
    assert config["variables"]["take_over_music"] is False
    validated = await async_validate_config_item(ctx.hass, "automation", config)
    assert validated is not None
    ctx.hass.states.async_set("input_boolean.follow", "on")
    ctx.hass.states.async_set("select.video", "TV")
    ctx.hass.states.async_set("media_player.zone", "playing", {"source": "Spotify"})
    variables = {
        **config["variables"],
        "trigger": {
            "from_state": State("select.video", "Other"),
            "to_state": State("select.video", "TV"),
        },
    }
    condition = Template(config["conditions"][0]["value_template"], ctx.hass)
    assert condition.async_render(variables) is False
    ctx.hass.states.async_set("media_player.zone", "playing", {"source": "AES67"})
    assert condition.async_render(variables) is True
    variables["trigger"]["to_state"] = State("select.video", "unknown")
    assert condition.async_render(variables) is False
