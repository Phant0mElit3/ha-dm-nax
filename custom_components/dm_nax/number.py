"""Number entities for Crestron DM NAX zone controls."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DmNaxApiError
from .const import DOMAIN
from .coordinator import DmNaxCoordinator
from .entity import DmNaxEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DmNaxZoneNumberDescription(NumberEntityDescription):
    """Description of a writable DM NAX zone number."""

    path: tuple[str, ...]
    native_scale: float
    scope: str = "audio"
    max_value_path: tuple[str, ...] | None = None
    support_path: tuple[str, ...] | None = None
    enabled_default: bool = False
    entity_category: EntityCategory | None = EntityCategory.CONFIG


DIRECT_NUMBER_DESCRIPTIONS = (
    DmNaxZoneNumberDescription(
        key="DefaultVolume",
        name="Default Volume",
        path=("DefaultVolume",),
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:volume-medium",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="MinVolume",
        name="Minimum Volume",
        path=("MinVolume",),
        native_min_value=0,
        native_max_value=50,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:volume-minus",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="MaxVolume",
        name="Maximum Volume",
        path=("MaxVolume",),
        native_min_value=70,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:volume-plus",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="MaxCastingVolume",
        name="Maximum Casting Volume",
        path=("MaxCastingVolume",),
        native_min_value=70,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:cast-audio",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="LineOutVolume",
        name="Line Out Volume",
        path=("LineOutVolume",),
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:audio-input-rca",
        native_scale=0.1,
        support_path=("IsLineOutSupported",),
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneNumberDescription(
        key="Bass",
        name="Bass",
        path=("Bass",),
        native_min_value=-12,
        native_max_value=12,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:equalizer",
        native_scale=0.1,
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneNumberDescription(
        key="Treble",
        name="Treble",
        path=("Treble",),
        native_min_value=-12,
        native_max_value=12,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:equalizer",
        native_scale=0.1,
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneNumberDescription(
        key="Balance",
        name="Balance",
        path=("Balance",),
        native_min_value=-50,
        native_max_value=50,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:scale-balance",
        native_scale=0.1,
        support_path=("IsBalanceSupported",),
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneNumberDescription(
        key="DelayInms",
        name="Delay",
        path=("DelayInms",),
        native_min_value=0,
        native_max_value=250,
        native_step=1,
        native_unit_of_measurement="ms",
        icon="mdi:timer-outline",
        native_scale=1,
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneNumberDescription(
        key="DuckedVolume",
        name="Ducked Volume",
        path=("DuckedVolume",),
        native_min_value=-80,
        native_max_value=20,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:volume-vibrate",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="BusVolumeOffset",
        name="Bus Volume Offset",
        path=("BusVolumeOffset",),
        native_min_value=-12,
        native_max_value=12,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:tune",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="MuteVolume",
        name="Mute Volume",
        path=("MuteVolume",),
        native_min_value=-80,
        native_max_value=20,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:volume-off",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="VolRampUpTimeInms",
        name="Volume Ramp Up",
        path=("VolRampUpTimeInms",),
        native_min_value=0,
        native_max_value=1000,
        native_step=1,
        native_unit_of_measurement="ms",
        icon="mdi:arrow-up-bold",
        native_scale=1,
    ),
    DmNaxZoneNumberDescription(
        key="VolRampDownTimeInms",
        name="Volume Ramp Down",
        path=("VolRampDownTimeInms",),
        native_min_value=0,
        native_max_value=1000,
        native_step=1,
        native_unit_of_measurement="ms",
        icon="mdi:arrow-down-bold",
        native_scale=1,
    ),
    DmNaxZoneNumberDescription(
        key="TestToneVolume",
        name="Test Tone Volume",
        path=("TestToneVolume",),
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:volume-source",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="CrossOverFrequencyInHz",
        name="Crossover Frequency",
        path=("CrossOverFrequencyInHz",),
        native_min_value=40,
        native_max_value=200,
        native_step=1,
        native_unit_of_measurement="Hz",
        icon="mdi:sine-wave",
        native_scale=1,
    ),
    DmNaxZoneNumberDescription(
        key="SubTrimLevel",
        name="Sub Trim",
        path=("SubTrimLevel",),
        native_min_value=-12,
        native_max_value=12,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:speaker",
        native_scale=0.1,
        support_path=("IsSubTrimLevelSupported",),
        enabled_default=True,
        entity_category=None,
    ),
    DmNaxZoneNumberDescription(
        key="SpeakerPower",
        name="Speaker Power",
        path=("Speaker", "Power"),
        native_min_value=5,
        native_max_value=150,
        native_step=1,
        native_unit_of_measurement="W",
        icon="mdi:speaker",
        native_scale=1,
        max_value_path=("Speaker", "PowerMax"),
        support_path=("IsAmplificationSupported",),
    ),
    DmNaxZoneNumberDescription(
        key="AnnouncementVolume",
        name="Announcement Volume",
        path=("Announcing", "Volume"),
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:bullhorn",
        native_scale=0.1,
        scope="zone",
    ),
    DmNaxZoneNumberDescription(
        key="AnnouncementDuckingLevel",
        name="Announcement Ducking Level",
        path=("Announcing", "DuckingLevel"),
        native_min_value=-80,
        native_max_value=0,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:volume-vibrate",
        native_scale=0.1,
        scope="zone",
    ),
    DmNaxZoneNumberDescription(
        key="AnnouncementRampTimeInms",
        name="Announcement Ramp Time",
        path=("Announcing", "RampTimeInms"),
        native_min_value=0,
        native_max_value=1000,
        native_step=1,
        native_unit_of_measurement="ms",
        icon="mdi:timer-outline",
        native_scale=1,
        scope="zone",
    ),
    DmNaxZoneNumberDescription(
        key="IntercomVolume",
        name="Intercom Volume",
        path=("Announcing", "Intercom", "Volume"),
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:account-voice",
        native_scale=0.1,
        scope="zone",
    ),
)


def _peq_number_descriptions() -> tuple[DmNaxZoneNumberDescription, ...]:
    descriptions: list[DmNaxZoneNumberDescription] = []
    for band_number in range(1, 11):
        band = f"Band{band_number:02d}"
        prefix = ("Peq", "Bands", band)
        label = f"PEQ {band}"
        descriptions.extend(
            [
                DmNaxZoneNumberDescription(
                    key=f"{band}Gain",
                    name=f"{label} Gain",
                    path=(*prefix, "Gain"),
                    native_min_value=-40,
                    native_max_value=20,
                    native_step=0.1,
                    native_unit_of_measurement="dB",
                    icon="mdi:equalizer",
                    native_scale=0.1,
                    max_value_path=(*prefix, "GainMax"),
                    support_path=(*prefix, "IsGainSupported"),
                ),
                DmNaxZoneNumberDescription(
                    key=f"{band}Frequency",
                    name=f"{label} Frequency",
                    path=(*prefix, "Frequency"),
                    native_min_value=10,
                    native_max_value=20000,
                    native_step=1,
                    native_unit_of_measurement="Hz",
                    icon="mdi:sine-wave",
                    native_scale=1,
                ),
                DmNaxZoneNumberDescription(
                    key=f"{band}Bandwidth",
                    name=f"{label} Bandwidth",
                    path=(*prefix, "Bandwidth"),
                    native_min_value=0.1,
                    native_max_value=4,
                    native_step=0.01,
                    native_unit_of_measurement=None,
                    icon="mdi:waves",
                    native_scale=0.01,
                    support_path=(*prefix, "IsBandwidthSupported"),
                ),
            ]
        )
    return tuple(descriptions)


NUMBER_DESCRIPTIONS = DIRECT_NUMBER_DESCRIPTIONS + _peq_number_descriptions()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DM NAX optional zone number controls."""
    coordinator: DmNaxCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        DmNaxZoneNumber(coordinator, item, description)
        for item in coordinator.data.get("output_channels", [])
        for description in NUMBER_DESCRIPTIONS
        if item.get("id") is not None and _description_supported(item, description)
    ]
    _LOGGER.info(
        "Created %s DM NAX zone number entities across %s zones",
        len(entities),
        len(coordinator.data.get("output_channels", [])),
    )
    async_add_entities(entities)


class DmNaxZoneNumber(DmNaxEntity, NumberEntity):
    """A writable DM NAX zone number."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: DmNaxCoordinator,
        item: dict[str, Any],
        description: DmNaxZoneNumberDescription,
    ) -> None:
        super().__init__(coordinator, item)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{self._device_id}_{self._id}_{_slug(description.path)}"
        )
        self._attr_icon = description.icon
        self._attr_entity_registry_enabled_default = description.enabled_default
        self._attr_entity_category = description.entity_category
        self._attr_native_min_value = description.native_min_value
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return f"{super().name} {self.entity_description.name}"

    @property
    def native_max_value(self) -> float:
        """Return the native maximum value."""
        description = self.entity_description
        if description.max_value_path is None:
            return description.native_max_value
        max_value = _value_at(self.item, description.max_value_path)
        if max_value is None:
            return description.native_max_value
        return min(description.native_max_value, float(max_value) * description.native_scale)

    @property
    def native_value(self) -> float | None:
        """Return the current native value."""
        value = _value_at(self.item, self.entity_description.path)
        if value is None:
            return None
        return float(value) * self.entity_description.native_scale

    async def async_set_native_value(self, value: float) -> None:
        """Set the zone number value."""
        description = self.entity_description
        native_value = max(description.native_min_value, min(self.native_max_value, float(value)))
        raw_value = round(native_value / description.native_scale)
        try:
            if description.scope == "zone":
                await self.coordinator.api.async_set_zone_value(
                    self._id,
                    description.path,
                    raw_value,
                )
            else:
                await self.coordinator.api.async_set_zone_audio_value(
                    self._id,
                    description.path,
                    raw_value,
                )
        except DmNaxApiError as err:
            raise HomeAssistantError(
                f"DM NAX {description.name} command failed: {err}"
            ) from err
        await self.coordinator.async_request_refresh()


def _description_supported(
    item: dict[str, Any],
    description: DmNaxZoneNumberDescription,
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
