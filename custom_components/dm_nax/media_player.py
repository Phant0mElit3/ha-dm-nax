"""Media player entities for Crestron DM NAX output channels."""

from __future__ import annotations

import math
from collections import Counter
from time import monotonic
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .api import DmNaxApiError
from .const import DOMAIN
from .coordinator import DmNaxCoordinator
from .entity import DmNaxEntity

DM_NAX_VOLUME_MAX = 1000
OPTIMISTIC_VOLUME_TIMEOUT = 2


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
        self._volume_before_command: int | None = None
        self._volume_generation = 0
        self._cancel_volume_timer = None

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return supported features."""
        features = (
            MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE
        )
        if self.source_list and self.item.get("route_id"):
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
        source_id = item.get("source_id")
        if source_id is None:
            return None
        return self._source_name_for_id(str(source_id))

    @property
    def source_list(self) -> list[str]:
        """Return available input source names."""
        return list(self._source_labels.values())

    @property
    def _source_labels(self) -> dict[str, str]:
        """Disambiguate duplicate names without collisions with literal labels."""
        items = [
            item
            for item in self.coordinator.data.get("input_channels", [])
            if item.get("id") is not None
        ]
        counts = Counter(_input_name(item) for item in items)
        labels = {}
        reserved = {
            _input_name(item) for item in items if counts[_input_name(item)] == 1
        }
        for item in items:
            source_id, name = str(item["id"]), _input_name(item)
            label = name
            if counts[name] > 1:
                label = f"{name} ({source_id})"
                while label in reserved:
                    label += f" ({source_id})"
            reserved.add(label)
            labels[source_id] = label
        return labels

    async def async_set_volume_level(self, volume: float) -> None:
        """Set output volume within both HA and device bounds."""
        if not math.isfinite(volume):
            raise HomeAssistantError("Volume must be a finite number")
        minimum = max(0, int(self.item.get("MinVolume", 0)))
        maximum = min(
            DM_NAX_VOLUME_MAX, int(self.item.get("MaxVolume", DM_NAX_VOLUME_MAX))
        )
        level = max(minimum, min(maximum, round(volume * DM_NAX_VOLUME_MAX)))
        self._volume_generation += 1
        generation = self._volume_generation
        before = self._polled_volume_raw
        try:
            await self.coordinator.api.async_set_output_volume(self._id, level)
        except DmNaxApiError as err:
            if generation == self._volume_generation:
                self._clear_optimistic_volume()
                self.async_write_ha_state()
            raise HomeAssistantError(f"DM NAX volume command failed: {err}") from err
        if generation != self._volume_generation:
            return
        self._volume_before_command = before
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
        route_id = self.item.get("route_id")
        if route_id is None:
            raise HomeAssistantError("DM NAX does not report a route for this output")
        try:
            await self.coordinator.api.async_set_audio_source(str(route_id), source_id)
        except DmNaxApiError as err:
            raise HomeAssistantError(f"DM NAX source command failed: {err}") from err
        await self.coordinator.async_request_refresh()

    def _source_id_for_name(self, name: str) -> str | None:
        """Return a route source id for a Home Assistant source name."""
        return next(
            (key for key, label in self._source_labels.items() if label == name), None
        )

    def _source_name_for_id(self, source_id: str) -> str | None:
        """Use the same label for feedback and selection, including source aliases."""
        source = self.coordinator.data.get("inputs_by_source_id", {}).get(source_id)
        key = str(source["id"]) if source else source_id
        return self._source_labels.get(key, source_id)

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic volume once DM NAX confirms it or the override expires."""
        if self._optimistic_volume is not None and (
            self.item.get("Volume") == self._optimistic_volume
            or self._polled_volume_raw == self._optimistic_volume
            or self._polled_volume_raw != self._volume_before_command
            or self._optimistic_volume_expired
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
        if self._cancel_volume_timer is not None:
            self._cancel_volume_timer()
        self._optimistic_volume = max(0, min(DM_NAX_VOLUME_MAX, int(volume)))
        self._optimistic_volume_expires_at = monotonic() + OPTIMISTIC_VOLUME_TIMEOUT
        self._cancel_volume_timer = async_call_later(
            self.hass, OPTIMISTIC_VOLUME_TIMEOUT, self._expire_volume
        )

    def _clear_optimistic_volume(self) -> None:
        """Clear optimistic volume state."""
        self._optimistic_volume = None
        self._optimistic_volume_expires_at = None
        if self._cancel_volume_timer is not None:
            self._cancel_volume_timer()
            self._cancel_volume_timer = None

    @callback
    def _expire_volume(self, _now) -> None:
        """Return to authoritative state even when no poll has arrived."""
        self._clear_optimistic_volume()
        self.async_write_ha_state()
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    async def async_will_remove_from_hass(self) -> None:
        self._clear_optimistic_volume()
        await super().async_will_remove_from_hass()


def _input_name(item: dict[str, Any]) -> str:
    """Return a display name for an input channel."""
    return str(item.get("Name") or item.get("name") or item.get("id"))


def _bounded_volume(value: float) -> float:
    """Return value clamped to Home Assistant's volume range."""
    return max(0.0, min(1.0, value))
