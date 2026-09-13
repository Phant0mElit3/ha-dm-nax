"""Shared entity helpers for Crestron DM NAX."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DmNaxCoordinator


class DmNaxEntity(CoordinatorEntity[DmNaxCoordinator]):
    """Base class for DM NAX entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DmNaxCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._id = str(item["id"])
        device_id = self._device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{self._id}"

    @property
    def item(self) -> dict[str, Any]:
        """Return the latest output channel payload."""
        for item in self.coordinator.data.get("output_channels", []):
            if str(item.get("id")) == self._id:
                return item
        return {}

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        item = self.item
        return item.get("Name") or item.get("name") or self._id

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return self.coordinator.last_update_success and bool(self.item)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for the DM NAX device."""
        info = self.coordinator.data.get("device_info", {})
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=info.get("Manufacturer", "Crestron"),
            model=info.get("Model", "DM NAX"),
            name=info.get("Name") or info.get("HostName") or "Crestron DM NAX",
            serial_number=info.get("SerialNumber"),
            sw_version=info.get("DeviceVersion"),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common diagnostic attributes."""
        item = self.item
        route = item.get("route") if isinstance(item.get("route"), dict) else {}
        return {
            "channel_id": self._id,
            "audio_type": item.get("AudioType"),
            "bus_id": item.get("BusId"),
            "is_bussed": item.get("IsBussed"),
            "is_channel_independent": item.get("IsChannelIndependent"),
            "is_signal_detected": item.get("IsSignalDetected"),
            "is_signal_clipping": item.get("IsSignalClipping"),
            "route_id": item.get("route_id"),
            "source_id": route.get("AudioSource", item.get("source_id")),
            "logical_zone_id": item.get("LogicalZoneId"),
            "nax_rx_stream": item.get("NaxRxStream"),
            "volume_db": item.get("VolumedB"),
        }

    @property
    def _device_id(self) -> str:
        """Return a stable device id."""
        info = self.coordinator.data.get("device_info", {})
        return str(info.get("DeviceId") or info.get("SerialNumber") or self.coordinator.api.base_url)
