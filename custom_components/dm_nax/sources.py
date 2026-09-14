"""Shared matrix source labels and commands for zone controls."""

from collections import Counter
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .api import DmNaxApiError
from .coordinator import DmNaxCoordinator


def source_labels(data: dict[str, Any]) -> dict[str, str]:
    """Disambiguate duplicate names without colliding with literal input names."""
    items = [
        item for item in data.get("input_channels", []) if item.get("id") is not None
    ]
    counts = Counter(_input_name(item) for item in items)
    labels = {}
    reserved = {_input_name(item) for item in items if counts[_input_name(item)] == 1}
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


def source_name(data: dict[str, Any], source_id: str) -> str | None:
    """Resolve route feedback through the same input IDs used for selection."""
    source = data.get("inputs_by_source_id", {}).get(source_id)
    key = str(source["id"]) if source else source_id
    return source_labels(data).get(key)


async def async_select_source(
    coordinator: DmNaxCoordinator, item: dict[str, Any], source: str
) -> None:
    """Change only the reported matrix route and reconcile device feedback."""
    source_id = next(
        (
            key
            for key, label in source_labels(coordinator.data).items()
            if label == source
        ),
        None,
    )
    if source_id is None:
        raise HomeAssistantError(f"Unknown DM NAX source: {source}")
    route_id = item.get("route_id")
    if route_id is None:
        raise HomeAssistantError("DM NAX does not report a route for this output")
    try:
        await coordinator.api.async_set_audio_source(str(route_id), source_id)
    except DmNaxApiError as err:
        raise HomeAssistantError(f"DM NAX source command failed: {err}") from err
    finally:
        await coordinator.async_request_refresh()


def _input_name(item: dict[str, Any]) -> str:
    return str(item.get("Name") or item.get("name") or item.get("id"))
