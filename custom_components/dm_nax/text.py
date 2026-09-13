"""Writable zone names for Crestron DM NAX."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DmNaxApiError
from .const import DOMAIN
from .coordinator import DmNaxCoordinator
from .entity import DmNaxEntity

ZONE_NAME_PATTERN = r"^(?!-)(?=.*\S)[^\r\n]{1,50}$"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up name controls for actual ZoneOutputs zones."""
    coordinator: DmNaxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DmNaxZoneName(coordinator, item)
        for item in coordinator.data.get("output_channels", [])
        if item.get("zone_id") is not None
    )


class DmNaxZoneName(DmNaxEntity, TextEntity):
    """Edit a zone's device-side name without changing its HA identity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = True
    _attr_icon = "mdi:rename-box"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 1
    _attr_native_max = 50
    _attr_pattern = ZONE_NAME_PATTERN

    def __init__(self, coordinator: DmNaxCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{self._id}_name"

    @property
    def name(self) -> str:
        """Keep the editing control labeled by its physical zone identifier."""
        return f"{self._id} Name"

    @property
    def native_value(self) -> str | None:
        """Return the name last reported by the device."""
        value = self.item.get("Name")
        return value if isinstance(value, str) else None

    async def async_set_value(self, value: str) -> None:
        """Rename the zone and reconcile its name through the coordinator."""
        if re.fullmatch(ZONE_NAME_PATTERN, value) is None:
            raise ServiceValidationError(
                "Zone names must contain 1-50 characters, cannot start with a dash, "
                "and cannot be blank or contain line breaks."
            )
        try:
            await self.coordinator.api.async_set_zone_value(self._id, ("Name",), value)
        except (DmNaxApiError, TimeoutError) as err:
            raise HomeAssistantError(f"DM NAX zone rename failed: {err}") from err
        await self.coordinator.async_request_refresh()
