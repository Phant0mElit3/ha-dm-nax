"""Media Player 2 protocol tests using a real local WebSocket server."""

import asyncio
import base64
from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from aiohttp import ClientSession, web
from homeassistant.exceptions import HomeAssistantError

from custom_components.dm_nax.api import DmNaxApiError
from custom_components.dm_nax.media import DmNaxMedia, auth_header, validate_credentials
from custom_components.dm_nax.stream_player import CONTENT_TYPE, DmNaxStreamPlayer

CLIENT = "56c659b7-2407-4085-8af9-42c4cb6b2c42"
SECRET = base64.b64encode(b"a" * 32).decode()
SIGNED = {
    "TagVersion": "1",
    "HmacTag": "opaque-signature",
    "SourceData": {
        "ProfileKey": "Profile1",
        "ProviderKey": "Provider7",
        "BrowseKey": "station-1",
        "Nonce": "opaque-nonce",
    },
}


def player(state="paused"):
    return {
        "PlayerState": state,
        "AvailableActions": ["Play", "Pause"],
        "Player": {
            "NowPlayingData": {
                "TrackTitle": "Test Track",
                "ArtistName": "Test Artist",
                "AlbumName": "Album",
                "Duration": 120,
            }
        },
    }


def test_auth_signature_matches_documented_hmac_format():
    url = "wss://example.invalid/subscriptionmgr"
    result = auth_header(url, CLIENT, SECRET, 123, "nonce")
    prefix, encoded = result.split(" ")
    assert prefix == "CrestronAuth-SHA256"
    content = base64.b64decode(encoded).decode()
    import hashlib
    import hmac

    expected = base64.b64encode(
        hmac.new(
            b"a" * 32, f"{CLIENT}GET{url}123nonce".encode(), hashlib.sha256
        ).digest()
    ).decode()
    assert content == f"{CLIENT}:{expected}:nonce:123"
    for client, secret in (
        ("bad", SECRET),
        (CLIENT, "bad"),
        (CLIENT, base64.b64encode(b"short").decode()),
    ):
        with pytest.raises(ValueError):
            validate_credentials(client, secret)


@pytest_asyncio.fixture
async def server():
    requests = []
    sockets = []

    async def handler(request):
        assert request.headers["Authorization"].startswith("CrestronAuth-SHA256 ")
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        sockets.append(ws)
        async for message in ws:
            data = message.json()
            requests.append(data)
            device = data["Device"]
            if "SubscriptionMgr" in device:
                action = device["SubscriptionMgr"]["RequestAction"]
                if action["RegistrationAction"] == "RegisterClient":
                    client = action["RegistrationActionOptions"][
                        "RegisteringClientIds"
                    ][0]
                    await ws.send_json(
                        {
                            "Device": {
                                "SubscriptionMgr": {
                                    "WsConnectionsList": {
                                        "Ws01": {
                                            "RegisteredClientList": {
                                                "session": {
                                                    "RegisteredClientId": client
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    )
                elif action["RegistrationAction"] == "GetCresNextObject":
                    await ws.send_json(
                        {
                            "Device": {
                                "MediaPlayerNeXt": {"Players": {"Player03": player()}}
                            }
                        }
                    )
                elif action["RegistrationAction"] == "SubscribeToObject":
                    paths = action["RegistrationActionOptions"]["CresNextPath"]
                    await ws.send_json(
                        {
                            "Device": {
                                "SubscriptionMgr": {
                                    "RegisteredClientList": {
                                        "session": {
                                            "SubscribedTo": {
                                                str(index): {"CresNextPath": path}
                                                for index, path in enumerate(paths)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    )
            elif "MediaPlayerNeXt" in device:
                action = device["MediaPlayerNeXt"]["RequestAction"]
                result = {
                    "PlayerState": "paused"
                    if action["ActionId"] == "Pause"
                    else "playing"
                }
                if action["ActionId"] == "LoadSource":
                    result["Player"] = {
                        "SignedData": action["ActionIdOptions"]["SignedData"]
                    }
                await ws.send_json(
                    {
                        "Device": {
                            "MediaPlayerNeXt": {"Players": {action["PlayerId"]: result}}
                        }
                    }
                )
            elif "MediaNavigation" in device:
                action = device["MediaNavigation"]["RequestAction"]
                await ws.send_json(
                    {
                        "Device": {
                            "MediaNavigation": {
                                "RegisteredClientMenus": {
                                    "session": {
                                        "LastRequestAction": {
                                            "MsgId": "stale",
                                            "CompletedTime": "old",
                                        }
                                    }
                                }
                            }
                        }
                    }
                )
                await ws.send_json(
                    {
                        "Device": {
                            "MediaNavigation": {
                                "RegisteredClientMenus": {
                                    "session": {
                                        "LastRequestAction": {
                                            "MsgId": action["MsgId"],
                                            "CompletedTime": "new",
                                        },
                                        "MenuUpdates": {
                                            "ProviderBrowseMenu": {
                                                "Categories": {
                                                    "Item01": {
                                                        "ItemOffset": 0,
                                                        "ItemCount": 1,
                                                        "TotalItemCount": 1,
                                                        "MenuDataItems": [
                                                            {
                                                                "BrowseItemName": "Radio",
                                                                "StreamingMediaType": "station",
                                                                "SignedData": SIGNED,
                                                            }
                                                        ],
                                                    }
                                                }
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    }
                )
        return ws

    app = web.Application()
    app.router.add_get("/subscriptionmgr", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    async with ClientSession() as session:
        media = DmNaxMedia(
            session,
            f"ws://127.0.0.1:{port}/subscriptionmgr",
            CLIENT,
            SECRET,
            False,
            Mock(),
        )
        try:
            yield media, requests
        finally:
            await media.close()
            for ws in sockets:
                await ws.close()
    await runner.cleanup()


@pytest.mark.asyncio
async def test_register_discover_subscribe_commands_deltas_and_close(server):
    media, requests = server
    await media.connect()
    assert media.connected and list(media.players) == ["Player03"]
    await media.command("Player03", "Play")
    assert media.players["Player03"]["PlayerState"] == "playing"
    assert (
        media.players["Player03"]["Player"]["NowPlayingData"]["TrackTitle"]
        == "Test Track"
    )
    await media.command("Player03", "Pause")
    assert media.players["Player03"]["PlayerState"] == "paused"
    token = media.remember({"secret": "private"})
    await media.close()
    assert not media.connected and media.reader is None and not media.players
    with pytest.raises(DmNaxApiError, match="expired"):
        media.cached(token)
    subscribe = requests[2]["Device"]["SubscriptionMgr"]["RequestAction"]
    assert subscribe["RegistrationActionOptions"]["CresNextPath"] == [
        "/Device/MediaPlayerNeXt/Players/Player03",
        "/Device/MediaNavigation/RegisteredClientMenus/session",
    ]
    assert all(
        "AvMatrixRouting" not in str(request) and "Volume" not in str(request)
        for request in requests
    )


@pytest.mark.asyncio
async def test_browse_signed_playback_and_no_route_takeover(ctx, server):
    media, requests = server
    await media.connect()
    ctx.coordinator.media = media
    ctx.coordinator.data["streaming_services"] = {
        "StreamingProviders": {"Provider7": {"AuthenticationType": "none"}},
        "UserProfiles": {
            "Profile1": {
                "Name": "Test",
                "AssignedProviders": {"Provider7": {"Name": "Radio"}},
            }
        },
    }
    entity = DmNaxStreamPlayer(ctx.coordinator, "Player03")
    root = await entity.async_browse_media()
    folder = await entity.async_browse_media(
        CONTENT_TYPE, root.children[0].media_content_id
    )
    assert folder.children[0].can_play
    await entity.async_play_media(CONTENT_TYPE, folder.children[0].media_content_id)
    assert entity.state == "playing"
    assert entity.media_title == "Test Track"
    assert entity.media_artist == "Test Artist"
    assert entity.media_duration == 120
    payload = requests[-1]["Device"]["MediaPlayerNeXt"]["RequestAction"]
    assert payload["ActionIdOptions"]["SignedData"] == SIGNED
    assert "HmacTag" not in str(entity.extra_state_attributes)
    assert ctx.item["Volume"] == 250 and ctx.item["IsMuted"]
    ctx.api.async_post_device.assert_not_awaited()
    with pytest.raises(HomeAssistantError, match="announcement"):
        await entity.async_play_media(
            CONTENT_TYPE, folder.children[0].media_content_id, announce=True
        )


@pytest.mark.asyncio
async def test_unsupported_commands_and_timeout_do_not_fake_state(server):
    media, _requests = server
    await media.connect()
    with pytest.raises(DmNaxApiError, match="does not offer"):
        await media.command("Player03", "Unsupported")
    media._send = AsyncMock()
    original_timeout = asyncio.timeout
    with (
        patch(
            "custom_components.dm_nax.media.asyncio.timeout",
            lambda _: original_timeout(0.01),
        ),
        pytest.raises(DmNaxApiError, match="not confirmed"),
    ):
        await media.command("Player03", "Play")
    assert media.players["Player03"]["PlayerState"] == "paused"
    assert not media._lock.locked()


@pytest.mark.asyncio
async def test_other_registered_client_does_not_supply_our_session():
    media = DmNaxMedia(
        Mock(), "wss://example.invalid/subscriptionmgr", CLIENT, SECRET, False, Mock()
    )
    media.consume(
        {
            "Device": {
                "SubscriptionMgr": {
                    "WsConnectionsList": {
                        "Ws01": {
                            "RegisteredClientList": {
                                "wrong-session": {
                                    "RegisteredClientId": "another-client"
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    assert media.rc_session is None


@pytest.mark.asyncio
async def test_browse_rejects_cross_profile_and_cache_is_bounded(server):
    media, _ = server
    await media.connect()
    original = deepcopy(SIGNED)
    with pytest.raises(DmNaxApiError, match="profile"):
        await media.browse("other-profile", "Provider7", SIGNED)
    assert SIGNED == original
    first = media.remember({"first": True})
    for index in range(1001):
        media.remember({"index": index})
    assert len(media._cache) == 1000
    with pytest.raises(DmNaxApiError):
        media.cached(first)


@pytest.mark.asyncio
async def test_disconnect_clears_availability_and_reconnects(server):
    media, _ = server
    await media.connect()
    await media.ws.close()
    async with asyncio.timeout(2):
        while media.connected:
            await asyncio.sleep(0)
    await media.connect()
    assert media.connected and media.players["Player03"]["PlayerState"] == "paused"


@pytest.mark.asyncio
async def test_pagination_uses_returned_count_not_requested_page_size(ctx, server):
    media, _ = server
    await media.connect()
    ctx.coordinator.media = media
    token = media.remember(
        {"profile": "Profile1", "provider": "Provider7", "playable": False}
    )
    media.browse = AsyncMock(
        return_value={
            "Categories": {
                "Item01": {
                    "ItemOffset": 0,
                    "ItemCount": 2,
                    "TotalItemCount": 10,
                    "MenuDataItems": [],
                }
            }
        }
    )
    directory = await DmNaxStreamPlayer(ctx.coordinator, "Player03").async_browse_media(
        CONTENT_TYPE, token
    )
    assert directory.children[0].title == "Next page"
    assert media.cached(directory.children[0].media_content_id)["offset"] == 2


@pytest.mark.asyncio
async def test_failed_mp2_connection_does_not_fail_zone_refresh(ctx):
    ctx.api.async_get_inventory = AsyncMock(
        return_value={
            "zones": {
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            "Zone2": {"Name": "Test", "ZoneAudio": {"Volume": 250}}
                        }
                    }
                }
            }
        }
    )
    ctx.coordinator.media = Mock(
        connected=False,
        connect=AsyncMock(side_effect=DmNaxApiError("offline")),
        close=AsyncMock(),
    )
    try:
        data = await ctx.coordinator._async_update_data()
        assert data["output_channels"][0]["Volume"] == 250
        await ctx.coordinator._media_connect_task
        assert ctx.coordinator._media_retry_at > ctx.hass.loop.time()
    finally:
        await ctx.coordinator.async_close_media()
