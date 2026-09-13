"""Exercise zone controls through Home Assistant's real entity registry."""

from datetime import timedelta
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.dm_nax import number, select, switch
from custom_components.dm_nax.const import DOMAIN
from custom_components.dm_nax.coordinator import DmNaxCoordinator


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "descriptions"),
    [
        (number, number.NUMBER_DESCRIPTIONS),
        (switch, switch.SWITCH_DESCRIPTIONS),
        (select, select.SELECT_DESCRIPTIONS),
    ],
    ids=["number", "switch", "select"],
)
async def test_zone_controls_register(tmp_path, caplog, module, descriptions):
    """Register every control and write enabled states without description errors."""
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    domain = module.__name__.rsplit(".", 1)[1]
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=domain,
        platform_name=DOMAIN,
        platform=module,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    try:
        assert await async_load_base_functionality(hass)
        coordinator = DmNaxCoordinator(hass, Mock(), scan_interval=None)
        zones = []
        for zone_id in ("Zone1", "Zone2"):
            zone = {"id": zone_id, "Name": zone_id}
            for description in descriptions:
                target = zone
                for key in description.path[:-1]:
                    target = target.setdefault(key, {})
                if module is number:
                    value = description.native_min_value / description.native_scale
                elif module is switch:
                    value = True
                else:
                    value = description.options[0]
                target[description.path[-1]] = value
            zones.append(zone)

        coordinator.async_set_updated_data(
            {"device_info": {"SerialNumber": "test-nax"}, "output_channels": zones}
        )
        entry = SimpleNamespace(entry_id="test-entry")
        hass.data[DOMAIN] = {entry.entry_id: coordinator}
        entities = []
        await module.async_setup_entry(hass, entry, entities.extend)
        assert len(entities) == 2 * len(descriptions)

        # This invokes the registration path that previously raised AttributeError.
        await platform.async_add_entities(entities)
        registry = er.async_get(hass)
        assert len(registry.entities) == len(entities)
        for entity in entities:
            registered = registry.async_get(entity.entity_id)
            assert registered is not None
            assert registered.hidden_by is None
            if entity.entity_description.enabled_default:
                assert registered.disabled_by is None
                assert registered.entity_category is None
                state = hass.states.get(entity.entity_id)
                assert state is not None
                assert state.state not in {"unknown", "unavailable"}
            else:
                assert registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION

        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    finally:
        await platform.async_reset()
        await hass.async_stop()
