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
    """Description of a writable DM NAX zone switch."""

    key: str
    name: str
    path: tuple[str, ...]
    icon: str
    scope: str = "audio"
    support_path: tuple[str, ...] | None = None
    enabled_default: bool = False


DIRECT_SWITCH_DESCRIPTIONS = (
    DmNaxZoneSwitchDescription(
        key="IsLoudnessEnabled",
        name="Loudness",
        path=("IsLoudnessEnabled",),
        icon="mdi:volume-high",
        enabled_default=True,
    ),
    DmNaxZoneSwitchDescription(
        key="IsDndEnabled",
        name="Do Not Disturb",
        path=("IsDndEnabled",),
        icon="mdi:minus-circle-outline",
        enabled_default=True,
    ),
    DmNaxZoneSwitchDescription(
        key="IsEqBypassEnabled",
        name="EQ Bypass",
        path=("IsEqBypassEnabled",),
        icon="mdi:equalizer-outline",
        enabled_default=True,
    ),
    DmNaxZoneSwitchDescription(
        key="IsLineOutEqBypassEnabled",
        name="Line Out EQ Bypass",
        path=("IsLineOutEqBypassEnabled",),
        icon="mdi:audio-input-rca",
        support_path=("IsLineOutSupported",),
        enabled_default=True,
    ),
    DmNaxZoneSwitchDescription(
        key="IsDuckingEnabled",
        name="Ducking",
        path=("IsDuckingEnabled",),
        icon="mdi:volume-vibrate",
        enabled_default=True,
    ),
    DmNaxZoneSwitchDescription(
        key="IsStereoEnabled",
        name="Stereo",
        path=("IsStereoEnabled",),
        icon="mdi:speaker-multiple",
        support_path=("IsStereoSelectionSupported",),
        enabled_default=True,
    ),
    DmNaxZoneSwitchDescription(
        key="IsTestToneActive",
        name="Test Tone",
        path=("IsTestToneActive",),
        icon="mdi:volume-source",
    ),
    DmNaxZoneSwitchDescription(
        key="IsCssEnabled",
        name="CSS",
        path=("IsCssEnabled",),
        icon="mdi:surround-sound",
        enabled_default=True,
    ),
    DmNaxZoneSwitchDescription(
        key="IsIdentifyActiveLeft",
        name="Identify Left",
        path=("IsIdentifyActiveLeft",),
        icon="mdi:led-on",
    ),
    DmNaxZoneSwitchDescription(
        key="IsIdentifyActiveRight",
        name="Identify Right",
        path=("IsIdentifyActiveRight",),
        icon="mdi:led-on",
    ),
    DmNaxZoneSwitchDescription(
        key="SpeakerIsOutputEnabled",
        name="Speaker Output",
        path=("Speaker", "IsOutputEnabled"),
        icon="mdi:speaker",
        support_path=("IsAmplificationSupported",),
    ),
    DmNaxZoneSwitchDescription(
        key="SpeakerIsSpeakerProtectEnabled",
        name="Speaker Protect",
        path=("Speaker", "IsSpeakerProtectEnabled"),
        icon="mdi:speaker-wireless",
        support_path=("Speaker", "IsSpeakerProtectSupported"),
    ),
    DmNaxZoneSwitchDescription(
        key="AirPlayEnabled",
        name="AirPlay",
        path=("ZoneBasedProviders", "Services", "AirPlay", "IsEnabled"),
        icon="mdi:cast-audio",
        scope="zone",
    ),
    DmNaxZoneSwitchDescription(
        key="SpotifyConnectEnabled",
        name="Spotify Connect",
        path=("ZoneBasedProviders", "Services", "SpotifyConnect", "IsEnabled"),
        icon="mdi:spotify",
        scope="zone",
    ),
)


def _peq_switch_descriptions() -> tuple[DmNaxZoneSwitchDescription, ...]:
    descriptions: list[DmNaxZoneSwitchDescription] = []
    for band_number in range(1, 11):
        band = f"Band{band_number:02d}"
        descriptions.append(
            DmNaxZoneSwitchDescription(
                key=f"{band}Bypass",
                name=f"PEQ {band} Bypass",
                path=("Peq", "Bands", band, "IsEqBypassEnabled"),
                icon="mdi:equalizer-outline",
            )
        )
    return tuple(descriptions)


SWITCH_DESCRIPTIONS = DIRECT_SWITCH_DESCRIPTIONS + _peq_switch_descriptions()


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
        if item.get("id") is not None and _description_supported(item, description)
    )


class DmNaxZoneSwitch(DmNaxEntity, SwitchEntity):
    """A writable DM NAX zone switch."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: DmNaxCoordinator,
        item: dict[str, Any],
        description: DmNaxZoneSwitchDescription,
    ) -> None:
        super().__init__(coordinator, item)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{self._device_id}_{self._id}_{_slug(description.path)}"
        )
        self._attr_icon = description.icon
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return f"{super().name} {self.entity_description.name}"

    @property
    def is_on(self) -> bool | None:
        """Return whether the switch is on."""
        value = _value_at(self.item, self.entity_description.path)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the zone switch on."""
        await self._async_set_switch(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the zone switch off."""
        await self._async_set_switch(False)

    async def _async_set_switch(self, value: bool) -> None:
        """Set the zone switch value."""
        description = self.entity_description
        try:
            if description.scope == "zone":
                await self.coordinator.api.async_set_zone_value(
                    self._id,
                    description.path,
                    value,
                )
            else:
                await self.coordinator.api.async_set_zone_audio_value(
                    self._id,
                    description.path,
                    value,
                )
        except DmNaxApiError as err:
            raise HomeAssistantError(
                f"DM NAX {description.name} command failed: {err}"
            ) from err
        await self.coordinator.async_request_refresh()


def _description_supported(
    item: dict[str, Any],
    description: DmNaxZoneSwitchDescription,
) -> bool:
    """Return whether a description is supported by this zone payload."""
    if _value_at(item, description.path) is None:
        return False
    if description.support_path is not None and _value_at(item, description.support_path) is False:
        return False
    return True


def _value_at(item: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Return a nested value from a zone item."""
    value: Any = item
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _slug(path: tuple[str, ...]) -> str:
    """Return a stable unique-id suffix from a property path."""
    return "_".join(part.lower() for part in path)
