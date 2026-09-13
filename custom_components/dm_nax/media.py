"""Optional Media Player 2 WebSocket client, separate from zone routing."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from contextlib import suppress
from copy import deepcopy
from uuid import UUID, uuid1, uuid4

from aiohttp import ClientError, WSMsgType

from .api import DmNaxApiError, _raise_for_action_results


def validate_credentials(client_id, secret):
    UUID(client_id)
    if len(base64.b64decode(secret, validate=True)) != 32:
        raise ValueError("Media client secret must decode to 32 bytes")


def auth_header(url, client_id, secret, timestamp=None, nonce=None):
    validate_credentials(client_id, secret)
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = nonce or str(uuid4())
    message = f"{client_id}GET{url}{timestamp}{nonce}".encode()
    signature = base64.b64encode(
        hmac.new(base64.b64decode(secret), message, hashlib.sha256).digest()
    ).decode()
    content = base64.b64encode(
        f"{client_id}:{signature}:{nonce}:{timestamp}".encode()
    ).decode()
    return f"CrestronAuth-SHA256 {content}"


def merge(target, update):
    """Merge device deltas, preserving fields absent from a partial notification."""
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = deepcopy(value)


class DmNaxMedia:
    def __init__(self, session, url, client_id, secret, verify_ssl, changed):
        self.session, self.url = session, url
        self.client_id, self.secret, self.verify_ssl = client_id, secret, verify_ssl
        self.changed = changed
        self.players = {}
        self.menu = {}
        self.rc_session = None
        self.ws = None
        self.reader = None
        self.connected = False
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._failure = None
        self._client_name = f"homeassistant-{uuid4()}"
        self._cache = {}
        self._subscriptions = set()

    async def connect(self):
        async with self._lock:
            if self.connected:
                return
            await self.close()
            try:
                async with asyncio.timeout(15):
                    self._failure = None
                    self.ws = await self.session.ws_connect(
                        self.url,
                        headers={
                            "Authorization": auth_header(
                                self.url, self.client_id, self.secret
                            )
                        },
                        ssl=self.verify_ssl,
                        heartbeat=20,
                        max_msg_size=4 * 1024 * 1024,
                    )
                    self.reader = asyncio.create_task(self._read())
                    await self._send(
                        "SubscriptionMgr",
                        {
                            "MsgId": str(uuid1()),
                            "RegistrationAction": "RegisterClient",
                            "RegistrationActionOptions": {
                                "RegisteringClientIds": [self._client_name]
                            },
                        },
                    )
                    await self._wait(lambda: self.rc_session is not None)
                    await self._send(
                        "SubscriptionMgr",
                        {
                            "MsgId": str(uuid1()),
                            "RegistrationAction": "GetCresNextObject",
                            "RegistrationActionOptions": {
                                "RcSessionId": self.rc_session,
                                "CresNextObject": "/Device/MediaPlayerNeXt/Players",
                            },
                        },
                    )
                    await self._wait(lambda: bool(self.players))
                    paths = [
                        f"/Device/MediaPlayerNeXt/Players/{key}" for key in self.players
                    ] + [
                        f"/Device/MediaNavigation/RegisteredClientMenus/{self.rc_session}"
                    ]
                    await self._send(
                        "SubscriptionMgr",
                        {
                            "MsgId": str(uuid1()),
                            "RegistrationAction": "SubscribeToObject",
                            "RegistrationActionOptions": {
                                "RcSessionId": self.rc_session,
                                "CresNextPath": paths,
                            },
                        },
                    )
                    await self._wait(lambda: set(paths) <= self._subscriptions)
                    self.connected = True
                    self.changed()
            except (TimeoutError, ClientError, ValueError, DmNaxApiError) as err:
                await self.close()
                raise DmNaxApiError(
                    "Media Player 2 connection failed; check mode and client credentials"
                ) from err

    async def close(self):
        self.connected = False
        if self.reader:
            self.reader.cancel()
            with suppress(asyncio.CancelledError):
                await self.reader
            self.reader = None
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.rc_session = None
        self.players.clear()
        self.menu.clear()
        self._cache.clear()
        self._subscriptions.clear()

    async def _read(self):
        try:
            async for message in self.ws:
                if message.type == WSMsgType.TEXT:
                    payload = json.loads(message.data)
                    for item in payload if isinstance(payload, list) else [payload]:
                        if isinstance(item, dict):
                            self.consume(item)
                elif message.type in (WSMsgType.ERROR, WSMsgType.CLOSED):
                    break
        except (ValueError, TypeError, AttributeError, ClientError, DmNaxApiError):
            self._failure = (
                "Media Player 2 returned an invalid response or rejected an action"
            )
        finally:
            self.connected = False
            self._failure = self._failure or "Media Player 2 disconnected"
            self._event.set()
            self.changed()

    def consume(self, payload):
        _raise_for_action_results(payload)
        device = payload.get("Device", {})
        connections = device.get("SubscriptionMgr", {}).get("WsConnectionsList", {})
        for connection in connections.values():
            for session_id, client in connection.get(
                "RegisteredClientList", {}
            ).items():
                if client.get("RegisteredClientId") == self._client_name:
                    self.rc_session = session_id
        subscriptions = (
            device.get("SubscriptionMgr", {})
            .get("RegisteredClientList", {})
            .get(self.rc_session, {})
            .get("SubscribedTo", {})
        )
        for value in subscriptions.values():
            if isinstance(value, dict) and isinstance(value.get("CresNextPath"), str):
                self._subscriptions.add(value["CresNextPath"])
        players = device.get("MediaPlayerNeXt", {}).get("Players", {})
        if isinstance(players, dict):
            merge(
                self.players,
                {
                    key: value
                    for key, value in players.items()
                    if isinstance(key, str)
                    and key.isalnum()
                    and isinstance(value, dict)
                },
            )
        menus = device.get("MediaNavigation", {}).get("RegisteredClientMenus", {})
        if self.rc_session in menus:
            merge(self.menu, menus[self.rc_session])
        self._event.set()
        self.changed()

    async def _send(self, object_name, action):
        if not self.ws or self.ws.closed:
            raise DmNaxApiError("Media Player 2 is disconnected")
        await self.ws.send_json({"Device": {object_name: {"RequestAction": action}}})

    async def _wait(self, predicate):
        while True:
            self._event.clear()
            if self._failure:
                raise DmNaxApiError(self._failure)
            if predicate():
                return
            await self._event.wait()

    async def command(self, player_id, action, options=None):
        async with self._lock:
            if not self.connected:
                raise DmNaxApiError("Configure and connect Media Player 2 first")
            player = self.players.get(player_id, {})
            if not player or (
                action != "LoadSource"
                and action not in player.get("AvailableActions", [])
            ):
                raise DmNaxApiError(
                    "The current player/provider does not offer this action"
                )
            if action not in ("Play", "Pause", "LoadSource"):
                raise DmNaxApiError("Unsupported playback action")
            if action == "LoadSource" and not isinstance(
                (options or {}).get("SignedData"), dict
            ):
                raise DmNaxApiError(
                    "Playback requires signed content from the media browser"
                )
            desired = "paused" if action == "Pause" else "playing"
            if action != "LoadSource" and player.get("PlayerState") == desired:
                return
            before = deepcopy(player)
            try:
                async with asyncio.timeout(15):
                    await self._send(
                        "MediaPlayerNeXt",
                        {
                            "RcSessionId": self.rc_session,
                            "MsgId": str(uuid1()),
                            "PlayerId": player_id,
                            "ActionId": action,
                            "ActionIdOptions": options or {},
                        },
                    )

                    def confirmed():
                        current = self.players.get(player_id, {})
                        if current.get("PlayerState") != desired:
                            return False
                        if action == "LoadSource":
                            return current.get("Player", {}).get("SignedData") == (
                                options or {}
                            ).get("SignedData")
                        return current != before

                    await self._wait(confirmed)
            except (TimeoutError, ClientError) as err:
                raise DmNaxApiError(
                    "Playback change was not confirmed by the NAX"
                ) from err

    def remember(self, item):
        # Signed navigation objects remain private, bounded and scoped to this connection.
        token = str(uuid4())
        if len(self._cache) >= 1000:
            self._cache.pop(next(iter(self._cache)))
        self._cache[token] = deepcopy(item)
        return token

    def cached(self, token):
        if token not in self._cache:
            raise DmNaxApiError("This browse item expired; reopen the media browser")
        return deepcopy(self._cache[token])

    async def browse(self, profile, provider, signed=None, offset=0):
        async with self._lock:
            if not self.connected:
                raise DmNaxApiError("Media Player 2 is disconnected")
            msg_id = str(uuid1())
            options = {
                "ProviderKey": provider,
                "BrowseKey": provider,
                "ItemCount": 50,
                "ItemOffset": offset,
            }
            if signed:
                source = signed["SourceData"]
                if (
                    source.get("ProfileKey") != profile
                    or source.get("ProviderKey") != provider
                ):
                    raise DmNaxApiError("Browse profile does not match signed content")
                options.update(BrowseKey=source["BrowseKey"], SignedData=signed)
            self.menu = {}
            try:
                async with asyncio.timeout(15):
                    await self._send(
                        "MediaNavigation",
                        {
                            "RcSessionId": self.rc_session,
                            "MsgId": msg_id,
                            "ProfileKey": profile,
                            "MenuCategory": "ProviderBrowseMenu",
                            "MenuCategoryOptions": options,
                        },
                    )
                    await self._wait(
                        lambda: (
                            self.menu.get("LastRequestAction", {}).get("MsgId")
                            == msg_id
                            and bool(
                                self.menu.get("LastRequestAction", {}).get(
                                    "CompletedTime"
                                )
                            )
                            and "ProviderBrowseMenu" in self.menu.get("MenuUpdates", {})
                        )
                    )
                    return deepcopy(self.menu["MenuUpdates"]["ProviderBrowseMenu"])
            except (TimeoutError, ClientError) as err:
                raise DmNaxApiError(
                    "The NAX did not return the requested media directory"
                ) from err
