"""Read-only signal, clipping and receiver health indicators."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import DOMAIN
from .monitoring import DmNaxMonitor, discover_monitors

DESCRIPTIONS = (
    ("zone", "IsSignalDetected", "Audio Signal", None),
    ("zone", "IsSignalClipping", "Audio Clipping", None),
    ("fault", "IsCriticalFaultDetected", "Critical Fault", None),
    ("fault", "IsDcFaultDetected", "DC Fault", None),
    ("fault", "IsOverCurrentConditionDetected", "Overcurrent", None),
    ("fault", "IsOverTemperatureConditionDetected", "Overtemperature", None),
    ("fault", "IsVoltageFaultDetected", "Voltage Fault", None),
    ("fault", "IsClippingDetected", "Amplifier Clipping", None),
)


async def async_setup_entry(hass, entry, async_add_entities):
    discover_monitors(
        hass.data[DOMAIN][entry.entry_id],
        entry,
        async_add_entities,
        DESCRIPTIONS,
        DmNaxBinarySensor,
    )


class DmNaxBinarySensor(DmNaxMonitor, BinarySensorEntity):
    @property
    def device_class(self):
        return (
            BinarySensorDeviceClass.SOUND
            if self.key == "IsSignalDetected"
            else BinarySensorDeviceClass.PROBLEM
        )

    @property
    def is_on(self):
        return self.value if isinstance(self.value, bool) else None
