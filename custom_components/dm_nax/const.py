"""Constants for the DM NAX integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "dm_nax"

CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_NAME = "DM NAX"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)

PLATFORMS = [
    "binary_sensor",
    "button",
    "media_player",
    "number",
    "select",
    "sensor",
    "switch",
    "text",
]
