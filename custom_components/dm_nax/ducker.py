"""Optional DuckerConfig controls using reported input/output IDs."""

from dataclasses import dataclass
from math import isfinite

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .api import DmNaxApiError
from .object_entity import DmNaxObjectEntity


@dataclass(frozen=True)
class DuckerNumber:
    key: str
    name: str
    minimum: int
    maximum: int
    scale: float
    unit: str


NUMBERS = (
    DuckerNumber("AttackTime", "Attack", 1, 20000, 0.1, "ms"),
    DuckerNumber("ReleaseTimeInms", "Release", 10, 4000, 1, "ms"),
    DuckerNumber("HoldTime", "Hold", 1, 200, 0.1, "s"),
    DuckerNumber("Threshold", "Threshold", -60, 0, 1, "dB"),
    DuckerNumber("Attenuation", "Attenuation", -800, 0, 0.1, "dB"),
)
GAIN = DuckerNumber("GainLevel", "Reference Gain", -1200, 0, 0.1, "dB")
SWITCHES = {"IsBypassEnabled": "Bypass", "IsDuckerActive": "Active"}


def setup_duckers(coordinator, entry, add, kind):
    seen = set()

    @callback
    def discover():
        entities = []
        for output, item in (coordinator.data or {}).get("ducker_outputs", {}).items():
            if not isinstance(item, dict):
                continue
            paths = [((), item)] + [
                (("DuckerInputs", key), value)
                for key, value in item.get("DuckerInputs", {}).items()
                if isinstance(value, dict)
            ]
            for prefix, values in paths:
                descriptors = (
                    ((GAIN,) if prefix else NUMBERS)
                    if kind == "number"
                    else (
                        {"IsDuckerReference": "Reference Enabled"}
                        if prefix
                        else SWITCHES
                    )
                )
                for descriptor in descriptors:
                    key = descriptor.key if kind == "number" else descriptor
                    value = values.get(key)
                    valid = (
                        type(value) in (float, int)
                        if kind == "number"
                        else type(value) is bool
                    )
                    identity = (output, *prefix, key)
                    if not valid or identity in seen:
                        continue
                    seen.add(identity)
                    cls = DmNaxDuckerNumber if kind == "number" else DmNaxDuckerSwitch
                    description = descriptor if kind == "number" else descriptors[key]
                    entities.append(
                        cls(coordinator, output, (*prefix, key), description)
                    )
        if entities:
            add(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DmNaxDucker(DmNaxObjectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:volume-minus"

    def __init__(self, coordinator, output, path, description):
        super().__init__(coordinator, "ducker_outputs", output)
        self.path, self.description = path, description
        self._attr_unique_id += "_" + "_".join(path)

    @property
    def name(self):
        label = (
            self.description.name
            if isinstance(self.description, DuckerNumber)
            else self.description
        )
        input_id = f" {self.path[1]}" if len(self.path) > 1 else ""
        return f"Ducker {self._id}{input_id} {label}"

    @property
    def value(self):
        value = self.item
        for key in self.path:
            value = value.get(key) if isinstance(value, dict) else None
        return value

    @property
    def available(self):
        return super().available and self.value is not None

    async def write(self, value):
        if not self.available:
            raise HomeAssistantError("Ducker control is unavailable")
        try:
            await self.coordinator.api.async_set_ducker_value(
                self._id, self.path, value
            )
        except DmNaxApiError as err:
            raise HomeAssistantError(f"NAX ducker command failed: {err}") from err
        finally:
            await self.coordinator.async_request_refresh()


class DmNaxDuckerNumber(DmNaxDucker, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, output, path, description):
        super().__init__(coordinator, output, path, description)
        self._attr_native_min_value = description.minimum * description.scale
        self._attr_native_max_value = description.maximum * description.scale
        self._attr_native_step = description.scale
        self._attr_native_unit_of_measurement = description.unit

    @property
    def native_value(self):
        return (
            self.value * self.description.scale
            if type(self.value) in (int, float)
            else None
        )

    async def async_set_native_value(self, value):
        description = self.description
        if (
            not isfinite(value)
            or not self.native_min_value <= value <= self.native_max_value
        ):
            raise HomeAssistantError("Ducker value is outside the supported range")
        await self.write(round(value / description.scale))


class DmNaxDuckerSwitch(DmNaxDucker, SwitchEntity):
    @property
    def is_on(self):
        return self.value if type(self.value) is bool else None

    async def async_turn_on(self, **kwargs):
        await self.write(True)

    async def async_turn_off(self, **kwargs):
        await self.write(False)
