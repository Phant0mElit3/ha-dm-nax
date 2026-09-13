"""Select entities for Crestron DM NAX zone controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .aes67 import (
    OFF,
    receiver_for_output,
    stream_endpoint,
    stream_options,
    stream_started,
    stream_stopped,
)
from .api import DmNaxApiError
from .const import DOMAIN
from .controls import (
    DmNaxControlEntity,
    async_setup_controls,
    is_zone,
)
from .controls import (
    value_at as _value_at,
)
from .coordinator import DmNaxCoordinator
from .entity import DmNaxEntity


@dataclass(frozen=True, kw_only=True)
class DmNaxZoneSelectDescription(SelectEntityDescription):
    """Description of a writable DM NAX zone select."""

    path: tuple[str, ...]
    options: tuple[str, ...]
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
                options=(
                    "EQ",
                    "Notch",
                    "TrebleShelf",
                    "BassShelf",
                    "LowPass",
                    "HighPass",
                ),
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
    async_setup_controls(
        coordinator, entry, async_add_entities, SELECT_DESCRIPTIONS, DmNaxZoneSelect
    )
    seen: set[str] = set()

    @callback
    def discover_stream_selects():
        data = coordinator.data or {}
        entities = []
        for item in data.get("output_channels", []):
            key = str(item.get("id"))
            if (
                item.get("id") is not None
                and key not in seen
                and receiver_for_output(item, data.get("nax_rx_streams", {}))
            ):
                seen.add(key)
                entities.append(DmNaxAes67StreamSelect(coordinator, item))
        if entities:
            async_add_entities(entities)

    discover_stream_selects()
    entry.async_on_unload(coordinator.async_add_listener(discover_stream_selects))


class DmNaxAes67StreamSelect(DmNaxEntity, SelectEntity):
    """Choose the AES67 feed for a zone, separately from its input source."""

    _attr_icon = "mdi:multicast"

    def __init__(self, coordinator, item):
        super().__init__(coordinator, item)
        self._attr_unique_id += "_aes67_stream"

    @property
    def name(self):
        return f"{super().name} AES67 Stream"

    @property
    def _receiver_id(self):
        return receiver_for_output(
            self.item, self.coordinator.data.get("nax_rx_streams", {})
        )

    @property
    def _receiver(self):
        return self.coordinator.data.get("nax_rx_streams", {}).get(
            self._receiver_id, {}
        )

    @property
    def available(self):
        return super().available and self._receiver_id is not None

    def _options(self):
        return stream_options(
            self.coordinator.data.get("nax_sdp_streams", {}),
            self.coordinator.stream_aliases,
        )

    @property
    def options(self):
        return list(self._options())

    @property
    def current_option(self):
        receiver = self._receiver
        if stream_stopped(receiver):
            return OFF
        if not stream_started(receiver) or not (endpoint := stream_endpoint(receiver)):
            return None
        streams = self.coordinator.data.get("nax_sdp_streams", {})
        matches = [
            label
            for label, key in self._options().items()
            if key is not None and stream_endpoint(streams[key]) == endpoint
        ]
        return matches[0] if len(matches) == 1 else None

    @property
    def extra_state_attributes(self):
        return {
            **super().extra_state_attributes,
            "aes67_stream_status": self._receiver.get("StreamStatus"),
        }

    async def async_select_option(self, option):
        options = self._options()
        if not self.available or option not in options:
            raise HomeAssistantError(
                "The AES67 receiver or selected stream is unavailable"
            )
        key = options[option]
        stream = (
            self.coordinator.data.get("nax_sdp_streams", {}).get(key)
            if key is not None
            else None
        )
        try:
            await self.coordinator.api.async_select_aes67_stream(
                self._receiver_id, stream
            )
        except DmNaxApiError as err:
            raise HomeAssistantError(f"DM NAX AES67 selection failed: {err}") from err
        finally:
            await self.coordinator.async_request_refresh()


class DmNaxZoneSelect(DmNaxControlEntity, SelectEntity):
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
        if description.key == "SpeakerImpedance" and not is_zone(self.item):
            return [*description.options, "NoSpeaker"]
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
            raise HomeAssistantError(
                f"Unknown DM NAX {description.name} option: {option}"
            )
        await self.async_write_control(option)


def _slug(path: tuple[str, ...]) -> str:
    """Return a stable unique-id suffix from a property path."""
    return "_".join(part.lower() for part in path)
