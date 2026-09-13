"""Device-level object entities with stable reported dictionary identities."""

from .entity import DmNaxEntity


class DmNaxObjectEntity(DmNaxEntity):
    def __init__(self, coordinator, bucket, key):
        self.bucket = bucket
        super().__init__(coordinator, {"id": key})
        self._attr_unique_id += f"_{bucket}"

    @property
    def item(self):
        value = self.coordinator.data.get(self.bucket, {}).get(self._id)
        return value if isinstance(value, dict) else {}

    @property
    def extra_state_attributes(self):
        return None
