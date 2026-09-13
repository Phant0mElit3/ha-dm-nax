"""Async client for the Crestron DM NAX CresNext API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .aes67 import stream_endpoint, stream_name, stream_started, stream_stopped

_LOGGER = logging.getLogger(__name__)

READ_ENDPOINTS = {
    "device_info": "/Device/DeviceInfo",
    "input_sources": "/Device/InputSources",
    "zone_outputs": "/Device/ZoneOutputs",
    "input_channels": "/Device/InputChannels",
    "output_channels": "/Device/OutputChannels",
    "av_matrix_routing": "/Device/AvMatrixRouting",
    "audio_ranges": "/Device/AudioRanges",
    "nax_audio": "/Device/NaxAudio",
}


class DmNaxApiError(Exception):
    """Raised when the DM NAX API returns an error."""


class DmNaxAuthError(DmNaxApiError):
    """Raised when DM NAX authentication fails."""


class DmNaxUnsupportedObjectError(DmNaxApiError):
    """Raised when a device does not implement an object."""


class DmNaxApi:
    """Small async client for DM NAX devices."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        username: str,
        password: str,
        *,
        use_ssl: bool = True,
        verify_ssl: bool = False,
        owns_session: bool = False,
    ) -> None:
        self._session = session
        self._host = _normalize_host(host)
        self._username = username
        self._password = password
        self._scheme = "https" if use_ssl else "http"
        self._verify_ssl = verify_ssl
        self._xsrf_token: str | None = None
        self._authenticated = False
        self._owns_session = owns_session
        self._request_lock = asyncio.Lock()
        self._timeout = ClientTimeout(total=10, connect=5)
        self._rx_locks: dict[str, asyncio.Lock] = {}

    @property
    def base_url(self) -> str:
        """Return the device base URL."""
        return f"{self._scheme}://{self._host}"

    async def async_close(self) -> None:
        """Release our session without closing Home Assistant's shared connector."""
        if not self._session.closed:
            if self._owns_session:
                await self._session.close()
            else:
                self._session.detach()

    async def async_login(self) -> None:
        """Begin an authenticated DM NAX web session."""
        async with self._request_lock:
            await self._async_login()

    async def _async_login(self) -> None:
        """Authenticate while holding the request lock."""
        self._authenticated = False
        self._xsrf_token = None
        login_url = f"{self.base_url}/userlogin.html"
        headers = self._browserish_headers()
        try:
            async with await self._session.get(
                login_url, headers=headers, ssl=self._verify_ssl, timeout=self._timeout
            ) as response:
                if response.status >= 400:
                    raise await _response_error(response)
                await response.read()
            async with await self._session.post(
                login_url,
                data={"login": self._username, "passwd": self._password},
                headers=headers,
                allow_redirects=False,
                ssl=self._verify_ssl,
                timeout=self._timeout,
            ) as response:
                if response.status not in (200, 302):
                    raise await _response_error(response)
                if response.status == 302 and response.headers.get("Location") not in (
                    None,
                    "/",
                ):
                    raise DmNaxAuthError("DM NAX login returned an unexpected redirect")
                self._xsrf_token = response.headers.get("CREST-XSRF-TOKEN")
                await response.read()
                self._authenticated = True
        except (ClientError, TimeoutError) as err:
            raise DmNaxApiError("Unable to connect to DM NAX device") from err

    async def _async_optional_object(self, key: str) -> dict[str, Any]:
        """Ignore only a confirmed unsupported endpoint, never a transport failure."""
        try:
            result = await self.async_get(READ_ENDPOINTS[key])
            _raise_for_action_results(result)
            return result
        except DmNaxUnsupportedObjectError:
            return {}

    async def async_get_inventory(self) -> dict[str, Any]:
        """Fetch state using the zone or channel object family actually available."""
        inventory = {"device_info": await self.async_get(READ_ENDPOINTS["device_info"])}
        for primary, alternate, object_name, child in (
            ("input_sources", "input_channels", "InputSources", "Inputs"),
            ("zone_outputs", "output_channels", "ZoneOutputs", "Zones"),
        ):
            payload = await self._async_optional_object(primary)
            inventory[primary] = payload
            if not payload.get("Device", {}).get(object_name, {}).get(child):
                inventory[alternate] = await self._async_optional_object(alternate)
        for key in ("av_matrix_routing", "audio_ranges", "nax_audio"):
            inventory[key] = await self._async_optional_object(key)
        return inventory

    async def async_get(self, path: str) -> dict[str, Any]:
        """Read a CresNext object path."""
        return await self._request("GET", path)

    async def async_post_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Post a partial Device object."""
        result = await self._request("POST", "/Device", json_payload=payload)
        _raise_for_action_results(result)
        return result

    async def async_set_output_volume(
        self, channel_id: str, volume: int
    ) -> dict[str, Any]:
        """Set output channel volume, where 0 is 0% and 1000 is 100%."""
        value = max(0, min(1000, int(volume)))
        if channel_id.startswith("Zone"):
            return await self.async_post_device(
                _zone_audio_payload(channel_id, {"Volume": value})
            )
        return await self.async_post_device(
            _output_channel_payload(channel_id, {"Volume": value})
        )

    async def async_set_output_mute(
        self, channel_id: str, muted: bool
    ) -> dict[str, Any]:
        """Set output channel mute state."""
        if channel_id.startswith("Zone"):
            return await self.async_post_device(
                _zone_audio_payload(channel_id, {"IsMuted": bool(muted)})
            )
        return await self.async_post_device(
            _output_channel_payload(channel_id, {"IsMuted": bool(muted)})
        )

    async def async_set_zone_audio_value(
        self,
        zone_id: str,
        key: str | Sequence[str],
        value: Any,
    ) -> dict[str, Any]:
        """Set one ZoneAudio property, including nested properties."""
        path = (key,) if isinstance(key, str) else tuple(key)
        return await self.async_post_device(
            _zone_audio_payload(zone_id, _nested_payload(path, value))
        )

    async def async_set_zone_value(
        self,
        zone_id: str,
        key: str | Sequence[str],
        value: Any,
    ) -> dict[str, Any]:
        """Set one zone property, including nested properties outside ZoneAudio."""
        path = (key,) if isinstance(key, str) else tuple(key)
        return await self.async_post_device(
            _zone_payload(zone_id, _nested_payload(path, value))
        )

    async def async_set_audio_source(
        self,
        route_id: str,
        audio_source: str | None,
    ) -> dict[str, Any]:
        """Route an input audio source to an output."""
        return await self.async_post_device(
            {
                "Device": {
                    "AvMatrixRouting": {
                        "Routes": {
                            route_id: {
                                "AudioSource": ""
                                if audio_source is None
                                else audio_source,
                            }
                        }
                    }
                }
            }
        )

    async def async_select_aes67_stream(
        self, receiver_id: str, stream: dict[str, Any] | None
    ) -> None:
        """Set one receive subscription without changing zone routing, mute or volume."""
        if not receiver_id or not receiver_id.isalnum():
            raise DmNaxApiError("Invalid AES67 receiver reference")
        endpoint = stream_endpoint(stream) if stream is not None else None
        if stream is not None and endpoint is None:
            raise DmNaxApiError(
                "The AES67 stream has no valid multicast address and port"
            )
        values: dict[str, Any] = {"StopRequested": True, "IsDisabled": True}
        if stream is not None:
            name = stream_name(stream)
            if name is None:
                raise DmNaxApiError(
                    "The discovered AES67 session name is not supported"
                )
            values = {
                "SessionNameRequested": name,
                "NetworkAddressRequested": endpoint[0],
                "PortRequested": endpoint[1],
                "IsDisabled": False,
                "StartRequested": True,
            }
        lock = self._rx_locks.setdefault(receiver_id, asyncio.Lock())
        async with lock:
            try:
                async with asyncio.timeout(15):
                    await self.async_post_device(
                        {
                            "Device": {
                                "NaxAudio": {
                                    "NaxRx": {"NaxRxStreams": {receiver_id: values}}
                                }
                            }
                        }
                    )
                    for _ in range(20):
                        data = await self.async_get(
                            f"/Device/NaxAudio/NaxRx/NaxRxStreams/{receiver_id}"
                        )
                        try:
                            received = data["Device"]["NaxAudio"]["NaxRx"][
                                "NaxRxStreams"
                            ][receiver_id]
                        except (KeyError, TypeError) as err:
                            raise DmNaxApiError(
                                "Missing AES67 receive readback"
                            ) from err
                        if not isinstance(received, dict):
                            raise DmNaxApiError("Invalid AES67 receive readback")
                        if stream is None and stream_stopped(received):
                            return
                        if (
                            stream is not None
                            and stream_started(received)
                            and stream_endpoint(received) == endpoint
                        ):
                            return
                        await asyncio.sleep(0.25)
                    raise DmNaxApiError(
                        "The NAX did not confirm the requested AES67 stream state"
                    )
            except TimeoutError as err:
                raise DmNaxApiError("Timed out waiting for AES67 reception") from err

    async def async_set_channel_value(
        self, channel_id: str, path: Sequence[str], value: Any
    ) -> dict[str, Any]:
        """Set a writable OutputChannels property."""
        return await self.async_post_device(
            _output_channel_payload(channel_id, _nested_payload(path, value))
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Serialize requests so credentials, XSRF tokens and writes stay ordered."""
        async with self._request_lock:
            try:
                for attempt in range(2 if retry_auth else 1):
                    if not self._authenticated:
                        await self._async_login()
                    headers = self._browserish_headers()
                    if method == "POST":
                        if not self._xsrf_token:
                            self._authenticated = False
                            raise DmNaxAuthError(
                                "DM NAX login did not return an XSRF token"
                            )
                        headers["X-CREST-XSRF-TOKEN"] = self._xsrf_token
                    url = f"{self.base_url}/{path.lstrip('/')}"
                    async with await self._session.request(
                        method,
                        url,
                        headers=headers,
                        json=json_payload,
                        ssl=self._verify_ssl,
                        timeout=self._timeout,
                    ) as response:
                        if response.status in (401, 403):
                            self._authenticated = False
                            self._xsrf_token = None
                            if attempt == 0 and retry_auth:
                                continue
                        if not 200 <= response.status < 300:
                            raise await _response_error(response)
                        if token := response.headers.get("CREST-XSRF-TOKEN"):
                            self._xsrf_token = token
                        if response.content_length == 0:
                            return {}
                        try:
                            payload = await response.json(content_type=None)
                        except ValueError as err:
                            raise DmNaxApiError(
                                "DM NAX returned a non-JSON response"
                            ) from err
                        if not isinstance(payload, dict):
                            raise DmNaxApiError(
                                "DM NAX returned an unexpected JSON payload"
                            )
                        return payload
            except (ClientError, TimeoutError) as err:
                raise DmNaxApiError("DM NAX request failed or timed out") from err
        raise DmNaxAuthError("DM NAX rejected the session")

    def _browserish_headers(self) -> dict[str, str]:
        """Return headers expected by the DM NAX web service."""
        return {
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/userlogin.html",
        }


def _normalize_host(host: str) -> str:
    """Return a host string without scheme or path."""
    value = host.strip()
    for prefix in ("https://", "http://"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
    return value.strip("/")


def _output_channel_payload(
    channel_id: str, values: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a narrow partial object for an output channel update."""
    return {
        "Device": {
            "OutputChannels": {
                "Channels": {
                    channel_id: dict(values),
                }
            }
        }
    }


def _zone_audio_payload(zone_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Build a narrow partial object for a zone audio update."""
    return {
        "Device": {
            "ZoneOutputs": {
                "Zones": {
                    zone_id: {
                        "ZoneAudio": dict(values),
                    }
                }
            }
        }
    }


def _zone_payload(zone_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Build a narrow partial object for a zone update."""
    return {
        "Device": {
            "ZoneOutputs": {
                "Zones": {
                    zone_id: dict(values),
                }
            }
        }
    }


def _nested_payload(path: Sequence[str], value: Any) -> dict[str, Any]:
    """Build a nested payload dictionary from a property path."""
    if not path:
        raise ValueError("path must contain at least one key")
    payload: dict[str, Any] = {}
    current = payload
    for key in path[:-1]:
        child: dict[str, Any] = {}
        current[key] = child
        current = child
    current[path[-1]] = value
    return payload


async def _response_error(response: ClientResponse) -> DmNaxApiError:
    """Build a useful error from an HTTP response."""
    if response.status in (401, 403):
        return DmNaxAuthError("DM NAX rejected the credentials or session")
    if response.status == 404:
        return DmNaxUnsupportedObjectError("DM NAX object is not supported")
    return DmNaxApiError(f"DM NAX request failed with HTTP {response.status}")


def _raise_for_action_results(payload: dict[str, Any]) -> None:
    """Raise when a CresNext Actions response reports failed property writes."""
    actions = payload.get("Actions")
    if not isinstance(actions, list):
        return
    failures: list[str] = []
    statuses: list[int] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        results = action.get("Results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            status_id = result.get("StatusId")
            if isinstance(status_id, int) and status_id != 0:
                statuses.append(status_id)
                path = result.get("Path", "unknown path")
                status = {
                    1: "Accepted; device reboot required",
                    2: "Accepted; application reset required",
                    3: "Unsupported operation",
                }.get(status_id, result.get("StatusInfo") or "unknown error")
                failures.append(f"{path}: {status} ({result.get('Property', '')})")
    if failures:
        if all(status == 3 for status in statuses):
            raise DmNaxUnsupportedObjectError("; ".join(failures))
        raise DmNaxApiError("; ".join(failures))
