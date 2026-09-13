"""Select entities for Crestron DM NAX zone controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity
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
class DmNaxZoneSelectDescription:
    """Description of a writable DM NAX zone select."""

    key: str
    name: str
    path: tuple[str, ...]
    options: tuple[str, ...]
    icon: str
    scope: str = "audio"
    options_path: tuple[str, ...] | None = None
    support_path: tuple[str, ...] | None = None
    enabled_default: bool = False
    entity_category: EntityCategory | None = EntityCategory.CONFIG


DIRECT_SELECT_DESCRIPTIONS = (
    DmNaxZoneSelectDescription(
        key="ToneProfile",
        name="Tone Profile",
        path=("ToneProfile",),
        options=("Off", "Classical", "Jazz", "Pop", "Rock", "SpokenWord"),
        icon="mdi:music-clef-treble",
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneSelectDescription(
        key="NightMode",
        name="Night Mode",
        path=("NightMode",),
        options=("Off", "Low", "Medium", "High"),
        icon="mdi:weather-night",
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneSelectDescription(
        key="SpeakerImpedance",
        name="Speaker Impedance",
        path=("Speaker", "Impedance"),
        options=("4ohm", "8ohm"),
        icon="mdi:omega",
        support_path=("Speaker", "IsImpedanceAdjustable"),
    ),
    DmNaxZoneSelectDescription(
        key="ZoneConfiguration",
        name="Zone Configuration",
        path=("ZoneConfiguration",),
        options=("Standard", "Bridged", "Bridged2p1", "BridgedSub2p1", "BridgedMono"),
        icon="mdi:speaker-multiple",
        scope="zone",
        options_path=("SupportedZoneConfigurations",),
    ),
)


def _peq_select_descriptions() -> tuple[DmNaxZoneSelectDescription, ...]:
    descriptions: list[DmNaxZoneSelectDescription] = []
    for band_number in range(1, 11):
        band = f"Band{band_number:02d}"
        descriptions.append(
            DmNaxZoneSelectDescription(
                key=f"{band}Type",
                name=f"PEQ {band} Type",
                path=("Peq", "Bands", band, "Type"),
                options=("EQ", "Notch", "TrebleShelf", "BassShelf", "LowPass", "HighPass"),
                icon="mdi:equalizer",
            )
        )
    return tuple(descriptions)


SELECT_DESCRIPTIONS = DIRECT_SELECT_DESCRIPTIONS + _peq_select_descriptions()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DM NAX optional zone selects."""
    coordinator: DmNaxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DmNaxZoneSelect(coordinator, item, description)
        for item in coordinator.data.get("output_channels", [])
        for description in SELECT_DESCRIPTIONS
        if item.get("id") is not None and _description_supported(item, description)
    )


class DmNaxZoneSelect(DmNaxEntity, SelectEntity):
    """A writable DM NAX zone select."""

    def __init__(
        self,
        coordinator: DmNaxCoordinator,
        item: dict[str, Any],
        description: DmNaxZoneSelectDescription,
    ) -> None:
        super().__init__(coordinator, item)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{self._device_id}_{self._id}_{_slug(description.path)}"
        )
        self._attr_icon = description.icon
        self._attr_entity_registry_enabled_default = description.enabled_default
        self._attr_entity_category = description.entity_category

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return f"{super().name} {self.entity_description.name}"

    @property
    def options(self) -> list[str]:
        """Return select options."""
        description = self.entity_description
        if description.options_path is not None:
            value = _value_at(self.item, description.options_path)
            if isinstance(value, list):
                return [str(option) for option in value]
        return list(description.options)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        value = _value_at(self.item, self.entity_description.path)
        return str(value) if value is not None else None

    async def async_select_option(self, option: str) -> None:
        """Set selected option."""
        description = self.entity_description
        if option not in self.options:
            raise HomeAssistantError(f"Unknown DM NAX {description.name} option: {option}")
        try:
            if description.scope == "zone":
                await self.coordinator.api.async_set_zone_value(
                    self._id,
                    description.path,
                    option,
                )
            else:
                await self.coordinator.api.async_set_zone_audio_value(
                    self._id,
                    description.path,
                    option,
                )
        except DmNaxApiError as err:
            raise HomeAssistantError(
                f"DM NAX {description.name} command failed: {err}"
            ) from err
        await self.coordinator.async_request_refresh()


def _description_supported(
    item: dict[str, Any],
    description: DmNaxZoneSelectDescription,
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
