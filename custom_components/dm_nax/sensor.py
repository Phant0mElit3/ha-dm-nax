"""Read-only NAX receive stream telemetry."""

from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .monitoring import DmNaxMonitor, discover_monitors

DESCRIPTIONS = (
    ("rx", "StreamStatus", "AES67 Status", None),
    ("rx", "ErrCode", "AES67 Error", None),
    ("rx", "EncodingFormat", "AES67 Format", None),
    ("rx", "EncodingSampleRate", "AES67 Sample Rate", "Hz"),
    ("rx", "Channels", "AES67 Channels", None),
)


async def async_setup_entry(hass, entry, async_add_entities):
    discover_monitors(
        hass.data[DOMAIN][entry.entry_id],
        entry,
        async_add_entities,
        DESCRIPTIONS,
        DmNaxSensor,
    )


class DmNaxSensor(DmNaxMonitor, SensorEntity):
    _attr_icon = "mdi:multicast"

    @property
    def native_value(self):
        value = self.value
        return (
            value
            if isinstance(value, (str, int, float)) and not isinstance(value, bool)
            else None
        )
