"""Playback of existing NAX chimes, retaining device-configured destinations."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .api import DmNaxApiError
from .const import DOMAIN
from .object_entity import DmNaxObjectEntity


def chimes(data):
    for collection in ("DefaultChimes", "CustomChimes"):
        values = data.get("door_chimes", {}).get(collection, {})
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, dict) and key.isalnum():
                    yield collection, key, value


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen = set()

    @callback
    def discover():
        entities = []
        for collection, key, item in chimes(coordinator.data or {}):
            identity = (collection, key)
            if identity not in seen and "PlaybackInProgress" in item:
                seen.add(identity)
                entities.append(DmNaxChime(coordinator, collection, key))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DmNaxChime(DmNaxObjectEntity, ButtonEntity):
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, collection, key):
        self.collection = collection
        super().__init__(coordinator, "door_chimes", key)
        self._attr_unique_id += f"_{collection}"

    @property
    def item(self):
        return (
            self.coordinator.data.get("door_chimes", {})
            .get(self.collection, {})
            .get(self._id, {})
        )

    @property
    def name(self):
        return f"Chime {self.item.get('Name') or self.item.get('FileName') or self._id}"

    @property
    def extra_state_attributes(self):
        return {
            "playback_in_progress": self.item.get("PlaybackInProgress"),
            "playback_zones": [
                key
                for key, value in self.item.get("PlaybackZones", {}).items()
                if isinstance(value, dict) and value.get("IsEnabled") is True
            ],
        }

    async def async_press(self):
        if not self.available:
            raise HomeAssistantError("Chime is unavailable")
        try:
            await self.coordinator.api.async_play_chime(self.collection, self._id)
        except DmNaxApiError as err:
            raise HomeAssistantError(f"NAX chime failed: {err}") from err
        finally:
            await self.coordinator.async_request_refresh()
