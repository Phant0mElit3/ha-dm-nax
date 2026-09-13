"""Shared discovery and capability checks for writable output controls."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .api import DmNaxApiError
from .entity import DmNaxEntity

_CHANNEL_WRITABLE = frozenset(
    {
        "DefaultVolume",
        "MinVolume",
        "MaxVolume",
        "Bass",
        "Treble",
        "DelayInms",
        "DuckedVolume",
        "BusVolumeOffset",
        "VolRampUpTimeInms",
        "VolRampDownTimeInms",
        "IsDuckingEnabled",
        "IsEqBypassEnabled",
        "Speaker",
        "Peq",
    }
)


def is_zone(item: dict[str, Any]) -> bool:
    """Identify the zone schema, including normalized output objects."""
    return item.get("zone_id") is not None or str(item.get("id", "")).startswith("Zone")


def control_path(item: dict[str, Any], path: tuple[str, ...]) -> tuple[str, ...]:
    """Map logical speaker controls to the channel amplifier object."""
    if not is_zone(item) and path[0] == "Speaker":
        return ("AmpOutput", *path[1:])
    return path


def value_at(item: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Read a control using the device's object family."""
    value: Any = item
    for key in control_path(item, path):
        if not isinstance(value, dict):
            return None
        if key == "IsBandwidthSupported" and key not in value:
            key = "IsBandwithSupported"
        value = value.get(key)
    return value


def description_supported(item: dict[str, Any], description) -> bool:
    """Require a writable property and current capability support."""
    if not is_zone(item) and (
        description.scope == "zone" or description.path[0] not in _CHANNEL_WRITABLE
    ):
        return False
    if value_at(item, description.path) is None:
        return False
    if description.support_path and value_at(item, description.support_path) is False:
        return False
    if (
        description.key == "ZoneConfiguration"
        and item.get("IsZoneIndependent") is not True
    ):
        return False
    return not (
        description.key == "CrossOverFrequencyInHz"
        and (
            item.get("IsZoneIndependent") is not True
            or item.get("ZoneConfiguration") not in ("Bridged2p1", "BridgedSub2p1")
        )
    )


def async_setup_controls(
    coordinator, entry, async_add_entities, descriptions, entity_class
):
    """Discover newly supported controls after every refresh without duplicate IDs."""
    seen: set[tuple[str, str]] = set()

    @callback
    def discover():
        entities = []
        for item in (coordinator.data or {}).get("output_channels", []):
            if item.get("id") is None:
                continue
            for description in descriptions:
                key = (str(item["id"]), description.key)
                if key not in seen and description_supported(item, description):
                    seen.add(key)
                    entities.append(entity_class(coordinator, item, description))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DmNaxControlEntity(DmNaxEntity):
    """An output control whose availability tracks its current capabilities."""

    @property
    def available(self) -> bool:
        return super().available and description_supported(
            self.item, self.entity_description
        )

    async def async_write_control(self, value: Any) -> None:
        """Recheck capabilities before dispatching a narrow property write."""
        description = self.entity_description
        if not self.available:
            raise HomeAssistantError(
                f"DM NAX {description.name} is not currently supported"
            )
        try:
            if not is_zone(self.item):
                await self.coordinator.api.async_set_channel_value(
                    self._id, control_path(self.item, description.path), value
                )
            elif description.scope == "zone":
                await self.coordinator.api.async_set_zone_value(
                    self._id, description.path, value
                )
            else:
                await self.coordinator.api.async_set_zone_audio_value(
                    self._id, description.path, value
                )
        except DmNaxApiError as err:
            raise HomeAssistantError(
                f"DM NAX {description.name} command failed: {err}"
            ) from err
        await self.coordinator.async_request_refresh()
