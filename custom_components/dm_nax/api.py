"""Async client for the Crestron DM NAX CresNext API."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

_LOGGER = logging.getLogger(__name__)

READ_ENDPOINTS = {
    "device_info": "/Device/DeviceInfo",
    "input_sources": "/Device/InputSources",
    "zone_outputs": "/Device/ZoneOutputs",
    "input_channels": "/Device/InputChannels",
    "output_channels": "/Device/OutputChannels",
    "av_matrix_routing": "/Device/AvMatrixRouting",
    "audio_ranges": "/Device/AudioRanges",
}


class DmNaxApiError(Exception):
    """Raised when the DM NAX API returns an error."""


class DmNaxAuthError(DmNaxApiError):
    """Raised when DM NAX authentication fails."""


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
    ) -> None:
        self._session = session
        self._host = _normalize_host(host)
        self._username = username
        self._password = password
        self._scheme = "https" if use_ssl else "http"
        self._verify_ssl = verify_ssl
        self._xsrf_token: str | None = None
        self._authenticated = False

    @property
    def base_url(self) -> str:
        """Return the device base URL."""
        return f"{self._scheme}://{self._host}"

    async def async_close(self) -> None:
        """Close the underlying session if Home Assistant has not already done so."""
        if not self._session.closed:
            await self._session.close()

    async def async_login(self) -> None:
        """Begin an authenticated DM NAX web session."""
        login_url = f"{self.base_url}/userlogin.html"
        headers = self._browserish_headers()
        try:
            get_response = await self._session.get(
                login_url,
                headers=headers,
                ssl=self._verify_ssl,
            )
            async with get_response:
                await get_response.read()
            response = await self._session.post(
                login_url,
                data={"login": self._username, "passwd": self._password},
                headers=headers,
                allow_redirects=False,
                ssl=self._verify_ssl,
            )
        except ClientError as err:
            raise DmNaxAuthError(f"Unable to connect to DM NAX device: {err}") from err

        async with response:
            if response.status not in (200, 302):
                raise DmNaxAuthError(f"DM NAX login failed with HTTP {response.status}")
            if response.status == 302 and response.headers.get("Location") not in (None, "/"):
                raise DmNaxAuthError("DM NAX login returned an unexpected redirect")
            self._xsrf_token = response.headers.get("CREST-XSRF-TOKEN")
            self._authenticated = True
            _LOGGER.debug("Authenticated to DM NAX host %s", self._host)

    async def async_get_inventory(self) -> dict[str, Any]:
        """Fetch the DM NAX objects used by Home Assistant entities."""
        inventory: dict[str, Any] = {}
        for key, path in READ_ENDPOINTS.items():
            try:
                inventory[key] = await self.async_get(path)
            except DmNaxApiError:
                if key not in {"input_channels", "output_channels"}:
                    raise
                _LOGGER.debug("Optional DM NAX object %s is unavailable", path)
                inventory[key] = {}
        return inventory

    async def async_get(self, path: str) -> dict[str, Any]:
        """Read a CresNext object path."""
        return await self._request("GET", path)

    async def async_post_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Post a partial Device object."""
        result = await self._request("POST", "/Device", json_payload=payload)
        _raise_for_action_results(result)
        return result

    async def async_set_output_volume(self, channel_id: str, volume: int) -> dict[str, Any]:
        """Set output channel volume, where 0 is 0% and 1000 is 100%."""
        value = max(0, min(1000, int(volume)))
        if channel_id.startswith("Zone"):
            return await self.async_post_device(_zone_audio_payload(channel_id, {"Volume": value}))
        return await self.async_post_device(_output_channel_payload(channel_id, {"Volume": value}))

    async def async_set_output_mute(self, channel_id: str, muted: bool) -> dict[str, Any]:
        """Set output channel mute state."""
        if channel_id.startswith("Zone"):
            return await self.async_post_device(
                _zone_audio_payload(channel_id, {"IsMuted": bool(muted)})
            )
        return await self.async_post_device(_output_channel_payload(channel_id, {"IsMuted": bool(muted)}))

    async def async_set_zone_audio_value(
        self,
        zone_id: str,
        key: str,
        value: Any,
    ) -> dict[str, Any]:
        """Set one direct ZoneAudio property."""
        return await self.async_post_device(_zone_audio_payload(zone_id, {key: value}))

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
                                "AudioSource": "" if audio_source is None else audio_source,
                            }
                        }
                    }
                }
            }
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Make an authenticated DM NAX request."""
        if not self._authenticated:
            await self.async_login()

        url = f"{self.base_url}{path if path.startswith('/') else f'/{path}'}"
        headers = self._browserish_headers()
        if method == "POST":
            if not self._xsrf_token:
                raise DmNaxAuthError("DM NAX login did not return an XSRF token")
            headers["X-CREST-XSRF-TOKEN"] = self._xsrf_token

        try:
            response = await self._session.request(
                method,
                url,
                headers=headers,
                json=json_payload,
                ssl=self._verify_ssl,
            )
        except ClientError as err:
            raise DmNaxApiError(f"DM NAX request failed: {err}") from err

        async with response:
            if response.status == 403 and retry_auth:
                self._authenticated = False
                self._xsrf_token = None
                await self.async_login()
                return await self._request(
                    method,
                    path,
                    json_payload=json_payload,
                    retry_auth=False,
                )
            if response.status < 200 or response.status >= 300:
                raise await _response_error(response)
            if method == "POST" and response.headers.get("CREST-XSRF-TOKEN"):
                self._xsrf_token = response.headers["CREST-XSRF-TOKEN"]
            if response.content_length == 0:
                return {}
            try:
                payload = await response.json(content_type=None)
            except Exception as err:  # noqa: BLE001 - response body diagnostics matter here.
                text = await response.text()
                raise DmNaxApiError(f"DM NAX returned non-JSON response: {text}") from err
            if not isinstance(payload, dict):
                raise DmNaxApiError("DM NAX returned an unexpected JSON payload")
            return payload

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


def _output_channel_payload(channel_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
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


async def _response_error(response: ClientResponse) -> DmNaxApiError:
    """Build a useful error from an HTTP response."""
    try:
        text = await response.text()
    except ClientError:
        text = ""
    if response.status == 403:
        return DmNaxAuthError("DM NAX rejected the credentials or session")
    return DmNaxApiError(f"DM NAX request failed with HTTP {response.status}: {text}")


def _raise_for_action_results(payload: dict[str, Any]) -> None:
    """Raise when a CresNext Actions response reports failed property writes."""
    actions = payload.get("Actions")
    if not isinstance(actions, list):
        return
    failures: list[str] = []
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
            if isinstance(status_id, int) and status_id < 0:
                path = result.get("Path", "unknown path")
                status = result.get("StatusInfo", "unknown error")
                failures.append(f"{path}: {status}")
    if failures:
        raise DmNaxApiError("; ".join(failures))
