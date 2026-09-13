"""Data coordinator for Crestron DM NAX."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DmNaxApi, DmNaxApiError, DmNaxAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class DmNaxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll DM NAX state."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DmNaxApi,
        *,
        scan_interval=DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            inventory = await self.api.async_get_inventory()
        except DmNaxAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DmNaxApiError as err:
            raise UpdateFailed(str(err)) from err
        device = _device_object(inventory)
        device_info = _object_at(device, "DeviceInfo")
        input_channels = _input_items(device)
        output_channels = _output_items(device)
        routes = _route_items(_object_at(device, "AvMatrixRouting", "Routes"))

        inputs_by_source_id = _input_source_map(input_channels)
        routes_by_output_id = _route_output_map(routes)
        outputs = [
            _enrich_output(output, routes_by_output_id, inputs_by_source_id)
            for output in output_channels
            if output.get("id") is not None
        ]

        data = {
            "device": device,
            "device_info": device_info,
            "input_channels": input_channels,
            "inputs_by_source_id": inputs_by_source_id,
            "output_channels": outputs,
            "routes": routes,
            "audio_ranges": _object_at(device, "AudioRanges"),
        }
        _LOGGER.debug(
            "DM NAX refreshed: model=%s, inputs=%s, outputs=%s, routes=%s",
            device_info.get("Model"),
            len(input_channels),
            len(outputs),
            len(routes),
        )
        return data


def _device_object(inventory: dict[str, Any]) -> dict[str, Any]:
    """Merge /Device payloads into one Device object."""
    device: dict[str, Any] = {}
    for payload in inventory.values():
        if not isinstance(payload, dict):
            continue
        value = payload.get("Device")
        if isinstance(value, dict):
            device.update(value)
    return device


def _object_at(payload: dict[str, Any], *path: str) -> dict[str, Any]:
    """Return a nested object from a dictionary."""
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _channel_items(channels: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a CresNext channel dictionary to item dictionaries."""
    items: list[dict[str, Any]] = []
    for key, value in channels.items():
        if not isinstance(value, dict):
            continue
        item = dict(value)
        item.setdefault("id", key)
        item.setdefault("key", key)
        item.setdefault("Name", key)
        item["number"] = _numeric_suffix(key)
        items.append(item)
    return items


def _input_items(device: dict[str, Any]) -> list[dict[str, Any]]:
    """Return input objects from the object family supported by the device."""
    input_sources = _object_at(device, "InputSources", "Inputs")
    if input_sources:
        return _channel_items(input_sources)
    return _channel_items(_object_at(device, "InputChannels", "Channels"))


def _output_items(device: dict[str, Any]) -> list[dict[str, Any]]:
    """Return output/zone objects from the object family supported by the device."""
    zones = _object_at(device, "ZoneOutputs", "Zones")
    if zones:
        return [_normalize_zone(item) for item in _channel_items(zones)]
    return _channel_items(_object_at(device, "OutputChannels", "Channels"))


def _normalize_zone(item: dict[str, Any]) -> dict[str, Any]:
    """Flatten ZoneOutputs ZoneAudio values into the output shape used by entities."""
    audio = item.get("ZoneAudio") if isinstance(item.get("ZoneAudio"), dict) else {}
    normalized = {**item, **audio}
    normalized["zone_id"] = item.get("id")
    normalized["id"] = item.get("id")
    normalized["Name"] = item.get("Name") or item.get("id")
    normalized["AudioType"] = "Zone"
    return normalized


def _route_items(routes: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a CresNext route dictionary to item dictionaries."""
    items: list[dict[str, Any]] = []
    for key, value in routes.items():
        if not isinstance(value, dict):
            continue
        item = dict(value)
        item.setdefault("id", item.get("Id", key))
        item.setdefault("key", key)
        item["number"] = _numeric_suffix(key) or _numeric_suffix(
            str(item.get("id", ""))
        )
        items.append(item)
    return items


def _input_source_map(inputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a lookup from common route source identifiers to input channels."""
    lookup: dict[str, dict[str, Any]] = {}
    for item in inputs:
        item_id = str(item.get("id"))
        number = item.get("number")
        candidates = {item_id, str(item.get("Id", "")), item_id.lower()}
        if number is not None and item_id.lower().startswith("input"):
            candidates.update({f"input{number}", f"Input{number}", f"Ch{number:03d}"})
        for candidate in candidates:
            if candidate:
                lookup[candidate] = item
    return lookup


def _route_output_map(routes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a lookup from common output identifiers to routes."""
    lookup: dict[str, dict[str, Any]] = {}
    for item in routes:
        item_id = str(item.get("id"))
        key = str(item.get("key"))
        number = item.get("number")
        candidates = {item_id, key, item_id.lower(), key.lower()}
        if number is not None:
            candidates.update({f"output{number}", f"Output{number}", f"Ch{number:03d}"})
        for candidate in candidates:
            if candidate:
                lookup[candidate] = item
    return lookup


def _enrich_output(
    output: dict[str, Any],
    routes_by_output_id: dict[str, dict[str, Any]],
    inputs_by_source_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Attach routing/source details to an output channel."""
    item = dict(output)
    route = _matching_route(item, routes_by_output_id)
    if route:
        item["route"] = route
        item["route_id"] = str(route.get("key") or route.get("id"))
        source_id = route.get("AudioSource")
        item["source_id"] = source_id
        source = inputs_by_source_id.get(str(source_id))
        if source:
            item["source_name"] = source.get("Name") or source.get("id")
    return item


def _matching_route(
    output: dict[str, Any],
    routes_by_output_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Find the matrix route for an output channel."""
    output_id = str(output.get("id"))
    number = output.get("number")
    candidates = [output_id, output_id.lower()]
    if number is not None:
        candidates.extend([f"output{number}", f"Output{number}", f"Ch{number:03d}"])
    for candidate in candidates:
        route = routes_by_output_id.get(candidate)
        if route:
            return route
    return {}


def _numeric_suffix(value: str) -> int | None:
    """Return the trailing integer from a channel/route identifier."""
    match = re.search(r"(\d+)$", value)
    if not match:
        return None
    return int(match.group(1))
