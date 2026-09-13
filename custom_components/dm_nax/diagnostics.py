"""Allowlisted diagnostics: never export credentials or raw device payloads."""

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    info = data.get("device_info", {})
    return {
        "model": info.get("Model"),
        "firmware": info.get("DeviceVersion"),
        "last_update_success": coordinator.last_update_success,
        "poll_seconds": coordinator.update_interval.total_seconds()
        if coordinator.update_interval
        else None,
        "input_count": len(data.get("input_channels", [])),
        "discovered_stream_count": len(data.get("nax_sdp_streams", {})),
        "alias_count": len(coordinator.stream_aliases),
        "media_player_configured": coordinator.media is not None,
        "media_player_connected": bool(
            coordinator.media and coordinator.media.connected
        ),
        "zones": [
            {
                "index": index,
                "fields": sorted(item),
                "independent": item.get("IsZoneIndependent"),
                "signal": item.get("IsSignalDetected"),
                "clipping": item.get("IsSignalClipping"),
                "has_receiver_mapping": bool(item.get("NaxRxStream")),
                "has_route": bool(item.get("route_id")),
            }
            for index, item in enumerate(data.get("output_channels", []), 1)
        ],
        "ducker_count": len(data.get("ducker_outputs", {})),
        "chime_counts": {
            key: len(value)
            for key, value in data.get("door_chimes", {}).items()
            if key in ("DefaultChimes", "CustomChimes") and isinstance(value, dict)
        },
    }
