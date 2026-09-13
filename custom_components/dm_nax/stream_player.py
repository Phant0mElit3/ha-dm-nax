"""Media Player 2 transport and signed-content browsing, independent of zone outputs."""

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .api import DmNaxApiError
from .object_entity import DmNaxObjectEntity

CONTENT_TYPE = "dm_nax_media"
PLAYABLE = {"song", "station", "album", "playlist", "track"}


def setup_players(coordinator, entry, add):
    if not coordinator.media:
        return
    seen = set()

    @callback
    def discover():
        if not coordinator.media:
            return
        entities = []
        for key, value in coordinator.media.players.items():
            if isinstance(value, dict) and key not in seen:
                seen.add(key)
                entities.append(DmNaxStreamPlayer(coordinator, key))
        if entities:
            add(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


def browse_node(title, token, *, playable=False, expandable=True, children=None):
    return BrowseMedia(
        title=title,
        media_class="music" if playable else "directory",
        media_content_type=CONTENT_TYPE,
        media_content_id=token,
        can_play=playable,
        can_expand=expandable,
        children=children,
    )


class DmNaxStreamPlayer(DmNaxObjectEntity, MediaPlayerEntity):
    _attr_icon = "mdi:play-network"

    def __init__(self, coordinator, key):
        super().__init__(coordinator, "media_players", key)

    @property
    def media(self):
        return self.coordinator.media

    @property
    def item(self):
        return self.media.players.get(self._id, {}) if self.media else {}

    @property
    def name(self):
        return f"Streaming {self._id}"

    @property
    def available(self):
        return bool(self.media and self.media.connected and self.item)

    @property
    def state(self):
        return {
            "playing": MediaPlayerState.PLAYING,
            "paused": MediaPlayerState.PAUSED,
            "stopped": MediaPlayerState.IDLE,
            "idle": MediaPlayerState.IDLE,
        }.get(self.item.get("PlayerState"))

    @property
    def supported_features(self):
        features = (
            MediaPlayerEntityFeature.BROWSE_MEDIA | MediaPlayerEntityFeature.PLAY_MEDIA
        )
        actions = self.item.get("AvailableActions", [])
        if "Play" in actions:
            features |= MediaPlayerEntityFeature.PLAY
        if "Pause" in actions:
            features |= MediaPlayerEntityFeature.PAUSE
        return features

    @property
    def _metadata(self):
        return self.item.get("Player", {}).get("NowPlayingData", {})

    @property
    def media_title(self):
        return self._metadata.get("TrackTitle") or self._metadata.get("StationName")

    @property
    def media_artist(self):
        return self._metadata.get("ArtistName")

    @property
    def media_album_name(self):
        return self._metadata.get("AlbumName")

    @property
    def media_duration(self):
        value = self._metadata.get("Duration")
        return value if type(value) in (int, float) and value >= 0 else None

    @property
    def extra_state_attributes(self):
        return {"player_id": self._id, "stream_state": self.item.get("StreamState")}

    async def _command(self, action, options=None):
        if not self.available:
            raise HomeAssistantError("Streaming player is unavailable")
        try:
            await self.media.command(self._id, action, options)
        except DmNaxApiError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_play(self):
        await self._command("Play")

    async def async_media_pause(self):
        await self._command("Pause")

    async def async_play_media(self, media_type, media_id, **kwargs):
        if kwargs.get("announce") or kwargs.get("enqueue"):
            raise HomeAssistantError(
                "Streaming playback does not support announcement mixing or enqueue"
            )
        if media_type != CONTENT_TYPE or not self.available:
            raise HomeAssistantError(
                "Choose content from this NAX player's media browser"
            )
        try:
            entry = self.media.cached(media_id)
            if not entry.get("playable") or not isinstance(entry.get("signed"), dict):
                raise DmNaxApiError("The selected item is not playable")
            await self._command(
                "LoadSource",
                {
                    "ProfileKey": entry["profile"],
                    "ProviderKey": entry["provider"],
                    "SignedData": entry["signed"],
                    "AutoPlay": True,
                },
            )
        except DmNaxApiError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        if not self.available:
            raise HomeAssistantError("Media Player 2 is unavailable")
        if media_content_type not in (None, CONTENT_TYPE):
            raise HomeAssistantError("Unsupported NAX media type")
        try:
            if not media_content_id:
                return self._root()
            entry = self.media.cached(media_content_id)
            menu = await self.media.browse(
                entry["profile"],
                entry["provider"],
                entry.get("signed"),
                entry.get("offset", 0),
            )
            children = []
            next_offset = None
            for category in menu.get("Categories", {}).values():
                if not isinstance(category, dict):
                    continue
                for item in category.get("MenuDataItems", []):
                    if not isinstance(item, dict):
                        continue
                    signed = item.get("SignedData")
                    if not isinstance(signed, dict) or not isinstance(
                        signed.get("SourceData"), dict
                    ):
                        continue
                    source = signed["SourceData"]
                    if (
                        source.get("ProfileKey") != entry["profile"]
                        or source.get("ProviderKey") != entry["provider"]
                    ):
                        continue
                    kind = str(item.get("StreamingMediaType", "")).lower()
                    playable = kind in PLAYABLE
                    token = self.media.remember(
                        {
                            "profile": entry["profile"],
                            "provider": entry["provider"],
                            "signed": signed,
                            "playable": playable,
                        }
                    )
                    children.append(
                        browse_node(
                            item.get("BrowseItemName") or "Media",
                            token,
                            playable=playable,
                            expandable=kind in ("dirmenu", "album", "playlist"),
                        )
                    )
                offset, count, total = (
                    category.get(key, 0)
                    for key in ("ItemOffset", "ItemCount", "TotalItemCount")
                )
                if (
                    all(type(value) is int for value in (offset, count, total))
                    and count > 0
                    and offset + count < total
                    and offset + count > entry.get("offset", 0)
                ):
                    next_offset = max(next_offset or 0, offset + count)
            if next_offset is not None:
                token = self.media.remember(
                    {**entry, "offset": next_offset, "playable": False}
                )
                children.append(browse_node("Next page", token))
            return browse_node(
                menu.get("ParentBrowseKey", {}).get("BrowseItemName") or "NAX Media",
                media_content_id,
                children=children,
            )
        except DmNaxApiError as err:
            raise HomeAssistantError(str(err)) from err

    def _root(self):
        services = self.coordinator.data.get("streaming_services", {})
        providers = services.get("StreamingProviders", {})
        children = []
        for profile_id, profile in services.get("UserProfiles", {}).items():
            if not isinstance(profile, dict) or profile.get("IsEnabled") is False:
                continue
            for provider_id, assigned in profile.get("AssignedProviders", {}).items():
                provider = providers.get(provider_id, {})
                if (
                    not isinstance(assigned, dict)
                    or provider.get("IsSupported") is False
                    or provider.get("IsZoneBased") is True
                ):
                    continue
                if (
                    assigned.get("IsAuthenticated") is not True
                    and provider.get("AuthenticationType") != "none"
                ):
                    continue
                token = self.media.remember(
                    {"profile": profile_id, "provider": provider_id, "playable": False}
                )
                name = assigned.get("Name") or provider.get("Name") or provider_id
                children.append(
                    browse_node(f"{name} ({profile.get('Name') or profile_id})", token)
                )
        return browse_node("NAX Music Services", "", children=children)
