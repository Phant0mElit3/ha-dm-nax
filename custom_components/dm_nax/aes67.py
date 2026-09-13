"""Discovery and receive-state helpers for AES67 stream selection."""

from __future__ import annotations

from collections import Counter
from ipaddress import ip_address
from typing import Any

OFF = "Off"


def stream_name(stream: dict[str, Any]) -> str | None:
    """Validate the session name accepted by the NAX receive object."""
    name = stream.get("SessionNameStatus")
    if (
        isinstance(name, str)
        and 1 <= len(name) <= 31
        and name.strip()
        and not name.startswith("-")
        and name.isprintable()
    ):
        return name
    return None


def stream_endpoint(stream: dict[str, Any]) -> tuple[str, int] | None:
    """Accept only a discovered multicast address and valid UDP port."""
    address, port = stream.get("NetworkAddressStatus"), stream.get("PortStatus")
    if (
        not isinstance(address, str)
        or type(port) is not int
        or not 1025 <= port <= 65535
    ):
        return None
    try:
        parsed = ip_address(address)
    except ValueError:
        return None
    return (str(parsed), port) if parsed.is_multicast else None


def stream_started(stream: dict[str, Any]) -> bool:
    return str(stream.get("StreamStatus", "")).casefold() in (
        "started",
        "stream started",
        "connected",
    )


def stream_stopped(stream: dict[str, Any]) -> bool:
    return str(stream.get("StreamStatus", "")).casefold() in (
        "stopped",
        "stream stopped",
    )


def stream_options(streams: dict[str, Any]) -> dict[str, str | None]:
    """Keep duplicate/reserved session names independently selectable."""
    names = {
        key: stream_name(value)
        for key, value in streams.items()
        if isinstance(value, dict)
        and stream_endpoint(value)
        and stream_name(value) is not None
    }
    counts = Counter(names.values())
    options: dict[str, str | None] = {OFF: None}
    for key, name in sorted(names.items(), key=lambda pair: (pair[1], pair[0])):
        label = f"{name} ({key})" if name == OFF or counts[name] > 1 else name
        while label in options:
            label += f" ({key})"
        options[label] = key
    return options


def receiver_for_output(item: dict[str, Any], receivers: dict[str, Any]) -> str | None:
    """Use the device's explicit reference, never assume zone number equals stream number."""
    key = item.get("NaxRxStream")
    if item.get("IsZoneIndependent") is False:
        return None
    return (
        key if isinstance(key, str) and isinstance(receivers.get(key), dict) else None
    )
