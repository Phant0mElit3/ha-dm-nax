"""Number entities for Crestron DM NAX zone controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
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
class DmNaxZoneNumberDescription:
    """Description of a writable DM NAX ZoneAudio number."""

    key: str
    name: str
    native_min_value: float
    native_max_value: float
    native_step: float
    native_unit_of_measurement: str | None
    icon: str
    native_scale: float


NUMBER_DESCRIPTIONS = (
    DmNaxZoneNumberDescription(
        key="DefaultVolume",
        name="Default Volume",
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
        native_min_value=51,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:volume-plus",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="MaxCastingVolume",
        name="Maximum Casting Volume",
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:cast-audio",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="LineOutVolume",
        name="Line Out Volume",
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:audio-input-rca",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="Bass",
        name="Bass",
        native_min_value=-12,
        native_max_value=12,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:equalizer",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="Treble",
        name="Treble",
        native_min_value=-12,
        native_max_value=12,
        native_step=0.1,
        native_unit_of_measurement="dB",
        icon="mdi:equalizer",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="Balance",
        name="Balance",
        native_min_value=-50,
        native_max_value=50,
        native_step=0.1,
        native_unit_of_measurement="%",
        icon="mdi:scale-balance",
        native_scale=0.1,
    ),
    DmNaxZoneNumberDescription(
        key="DelayInms",
        name="Delay",
        native_min_value=0,
        native_max_value=250,
        native_step=1,
        native_unit_of_measurement="ms",
        icon="mdi:timer-outline",
        native_scale=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DM NAX optional zone number controls."""
    coordinator: DmNaxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DmNaxZoneNumber(coordinator, item, description)
        for item in coordinator.data.get("output_channels", [])
        for description in NUMBER_DESCRIPTIONS
        if item.get("id") is not None and description.key in item
    )


class DmNaxZoneNumber(DmNaxEntity, NumberEntity):
    """A disabled-by-default writable DM NAX zone number."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: DmNaxCoordinator,
        item: dict[str, Any],
        description: DmNaxZoneNumberDescription,
    ) -> None:
        super().__init__(coordinator, item)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{self._device_id}_{self._id}_{description.key.lower()}"
        )
        self._attr_icon = description.icon
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return f"{super().name} {self.entity_description.name}"

    @property
    def native_value(self) -> float | None:
        """Return the current native value."""
        value = self.item.get(self.entity_description.key)
        if value is None:
            return None
        return float(value) * self.entity_description.native_scale

    async def async_set_native_value(self, value: float) -> None:
        """Set the zone number value."""
        raw_value = round(float(value) / self.entity_description.native_scale)
        raw_value = max(
            round(self.entity_description.native_min_value / self.entity_description.native_scale),
            min(
                round(
                    self.entity_description.native_max_value
                    / self.entity_description.native_scale
                ),
                raw_value,
            ),
        )
        try:
            await self.coordinator.api.async_set_zone_audio_value(
                self._id,
                self.entity_description.key,
                raw_value,
            )
        except DmNaxApiError as err:
            raise HomeAssistantError(
                f"DM NAX {self.entity_description.name} command failed: {err}"
            ) from err
        await self.coordinator.async_request_refresh()

