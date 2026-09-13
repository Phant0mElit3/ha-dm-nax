"""Capability-driven zone telemetry shared by sensor platforms."""

from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .aes67 import receiver_for_output
from .controls import value_at
from .entity import DmNaxEntity


def discover_monitors(coordinator, entry, add, descriptions, entity_class):
    seen = set()

    @callback
    def discover():
        entities = []
        for item in (coordinator.data or {}).get("output_channels", []):
            for scope, key, label, unit in descriptions:
                identity = (item["id"], scope, key)
                entity = entity_class(coordinator, item, scope, key, label, unit)
                if identity not in seen and entity.value is not None:
                    seen.add(identity)
                    entities.append(entity)
        if entities:
            add(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DmNaxMonitor(DmNaxEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, item, scope, key, label, unit):
        super().__init__(coordinator, item)
        self.scope, self.key, self.label = scope, key, label
        self._attr_unique_id += f"_status_{scope}_{key.lower()}"
        self._attr_native_unit_of_measurement = unit

    @property
    def name(self):
        return f"{super().name} {self.label}"

    @property
    def value(self):
        if self.scope == "zone":
            return self.item.get(self.key)
        if self.scope == "fault":
            return value_at(self.item, ("Speaker", "Faults", self.key))
        receivers = self.coordinator.data.get("nax_rx_streams", {})
        return receivers.get(receiver_for_output(self.item, receivers), {}).get(
            self.key
        )

    @property
    def available(self):
        return super().available and self.value is not None

    @property
    def extra_state_attributes(self):
        return {"channel_id": self._id}
