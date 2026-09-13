"""Media player entities for Crestron DM NAX output channels."""

from __future__ import annotations

from time import monotonic
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DmNaxApiError
from .const import DOMAIN
from .coordinator import DmNaxCoordinator
from .entity import DmNaxEntity

DM_NAX_VOLUME_MAX = 1000
OPTIMISTIC_VOLUME_TIMEOUT = 30


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DM NAX output channel media players."""
    coordinator: DmNaxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DmNaxOutputChannel(coordinator, item)
        for item in coordinator.data.get("output_channels", [])
        if item.get("id") is not None
    )


class DmNaxOutputChannel(DmNaxEntity, MediaPlayerEntity):
    """A DM NAX output channel as a Home Assistant media player."""

    def __init__(self, coordinator: DmNaxCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item)
        self._optimistic_volume: int | None = None
        self._optimistic_volume_expires_at: float | None = None

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return supported features."""
        features = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE
        if self.source_list:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        return features

    @property
    def state(self) -> MediaPlayerState:
        """Return current output state."""
        item = self.item
        if item.get("IsMuted") is True:
            return MediaPlayerState.IDLE
        if item.get("IsSignalDetected") is True:
            return MediaPlayerState.PLAYING
        if item:
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        """Return current channel volume as 0.0-1.0."""
        if self._optimistic_volume is not None and not self._optimistic_volume_expired:
            return _bounded_volume(self._optimistic_volume / DM_NAX_VOLUME_MAX)
        self._clear_optimistic_volume()
        return self._polled_volume_level

    @property
    def _polled_volume_level(self) -> float | None:
        """Return the latest polled channel volume as 0.0-1.0."""
        volume = self._polled_volume_raw
        if volume is None:
            return None
        return _bounded_volume(volume / DM_NAX_VOLUME_MAX)

    @property
    def _polled_volume_raw(self) -> int | None:
        """Return the latest polled raw DM NAX volume."""
        volume = self.item.get("Volume")
        if volume is None:
            return None
        return int(volume)

    @property
    def is_volume_muted(self) -> bool | None:
        """Return whether the channel is muted."""
        muted = self.item.get("IsMuted")
        return muted if isinstance(muted, bool) else None

    @property
    def source(self) -> str | None:
        """Return the selected input source name."""
        item = self.item
        if item.get("source_name") is not None:
            return str(item["source_name"])
        source_id = item.get("source_id")
        if source_id is None:
            return None
        return self._source_name_for_id(str(source_id))

    @property
    def source_list(self) -> list[str]:
        """Return available input source names."""
        return [
            _input_name(item)
            for item in self.coordinator.data.get("input_channels", [])
            if item.get("id") is not None
        ]

    async def async_set_volume_level(self, volume: float) -> None:
        """Set output volume."""
        level = round(max(0.0, min(1.0, float(volume))) * DM_NAX_VOLUME_MAX)
        try:
            await self.coordinator.api.async_set_output_volume(self._id, level)
        except DmNaxApiError as err:
            raise HomeAssistantError(f"DM NAX volume command failed: {err}") from err
        self._set_optimistic_volume(level)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute output."""
        try:
            await self.coordinator.api.async_set_output_mute(self._id, mute)
        except DmNaxApiError as err:
            raise HomeAssistantError(f"DM NAX mute command failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select an input source for this output."""
        source_id = self._source_id_for_name(source)
        if source_id is None:
            raise HomeAssistantError(f"Unknown DM NAX source: {source}")
        route_id = self.item.get("route_id") or self._id
        try:
            await self.coordinator.api.async_set_audio_source(str(route_id), source_id)
        except DmNaxApiError as err:
            raise HomeAssistantError(f"DM NAX source command failed: {err}") from err
        await self.coordinator.async_request_refresh()

    def _source_id_for_name(self, name: str) -> str | None:
        """Return a route source id for a Home Assistant source name."""
        for item in self.coordinator.data.get("input_channels", []):
            if _input_name(item) == name:
                return str(item.get("id"))
        return None

    def _source_name_for_id(self, source_id: str) -> str | None:
        """Return a source display name for a route source id."""
        source = self.coordinator.data.get("inputs_by_source_id", {}).get(source_id)
        if source:
            return _input_name(source)
        return source_id

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic volume once DM NAX confirms it or the override expires."""
        if (
            self._optimistic_volume is not None
            and (
                self.item.get("Volume") == self._optimistic_volume
                or self._polled_volume_raw == self._optimistic_volume
                or self._optimistic_volume_expired
            )
        ):
            self._clear_optimistic_volume()
        super()._handle_coordinator_update()

    @property
    def _optimistic_volume_expired(self) -> bool:
        """Return whether the optimistic volume state is stale."""
        return (
            self._optimistic_volume_expires_at is not None
            and monotonic() >= self._optimistic_volume_expires_at
        )

    def _set_optimistic_volume(self, volume: int) -> None:
        """Temporarily reflect an accepted volume command before the next poll."""
        self._optimistic_volume = max(0, min(DM_NAX_VOLUME_MAX, int(volume)))
        self._optimistic_volume_expires_at = monotonic() + OPTIMISTIC_VOLUME_TIMEOUT

    def _clear_optimistic_volume(self) -> None:
        """Clear optimistic volume state."""
        self._optimistic_volume = None
        self._optimistic_volume_expires_at = None


def _input_name(item: dict[str, Any]) -> str:
    """Return a display name for an input channel."""
    return str(item.get("Name") or item.get("name") or item.get("id"))


def _bounded_volume(value: float) -> float:
    """Return value clamped to Home Assistant's volume range."""
    return max(0.0, min(1.0, value))
