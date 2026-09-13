"""Switch entities for Crestron DM NAX zone controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DmNaxApiError
from .const import DOMAIN
from .coordinator import DmNaxCoordinator
from .entity import DmNaxEntity


@dataclass(frozen=True)
class DmNaxZoneSwitchDescription:
    """Description of a writable DM NAX ZoneAudio switch."""

    key: str
    name: str
    icon: str


SWITCH_DESCRIPTIONS = (
    DmNaxZoneSwitchDescription(
        key="IsLoudnessEnabled",
        name="Loudness",
        icon="mdi:volume-high",
    ),
    DmNaxZoneSwitchDescription(
        key="IsDndEnabled",
        name="Do Not Disturb",
        icon="mdi:minus-circle-outline",
    ),
    DmNaxZoneSwitchDescription(
        key="IsEqBypassEnabled",
        name="EQ Bypass",
        icon="mdi:equalizer-outline",
    ),
    DmNaxZoneSwitchDescription(
        key="IsLineOutEqBypassEnabled",
        name="Line Out EQ Bypass",
        icon="mdi:audio-input-rca",
    ),
    DmNaxZoneSwitchDescription(
        key="IsDuckingEnabled",
        name="Ducking",
        icon="mdi:volume-vibrate",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DM NAX optional zone switches."""
    coordinator: DmNaxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DmNaxZoneSwitch(coordinator, item, description)
        for item in coordinator.data.get("output_channels", [])
        for description in SWITCH_DESCRIPTIONS
        if item.get("id") is not None and description.key in item
    )


class DmNaxZoneSwitch(DmNaxEntity, SwitchEntity):
    """A disabled-by-default writable DM NAX zone switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DmNaxCoordinator,
        item: dict[str, Any],
        description: DmNaxZoneSwitchDescription,
    ) -> None:
        super().__init__(coordinator, item)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{self._device_id}_{self._id}_{description.key.lower()}"
        )
        self._attr_icon = description.icon

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return f"{super().name} {self.entity_description.name}"

    @property
    def is_on(self) -> bool | None:
        """Return whether the switch is on."""
        value = self.item.get(self.entity_description.key)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the zone switch on."""
        await self._async_set_switch(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the zone switch off."""
        await self._async_set_switch(False)

    async def _async_set_switch(self, value: bool) -> None:
        """Set the zone switch value."""
        try:
            await self.coordinator.api.async_set_zone_audio_value(
                self._id,
                self.entity_description.key,
                value,
            )
        except DmNaxApiError as err:
            raise HomeAssistantError(
                f"DM NAX {self.entity_description.name} command failed: {err}"
            ) from err
        await self.coordinator.async_request_refresh()

