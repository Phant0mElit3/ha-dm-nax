# Crestron DM NAX for Home Assistant

Home Assistant custom integration for Crestron DM NAX audio devices using the local CresNext REST API.

This integration has been tested against a `DM-NAX-8ZSA` running firmware `3.2.0121.01081`.

## Features

- UI config flow.
- HTTPS login using the DM NAX web UI credentials.
- Local polling.
- One `media_player` entity per zone.
- Zone volume, mute, and source selection.
- Optional disabled-by-default zone controls:
  - Bass
  - Treble
  - Balance
  - Delay
  - Default volume
  - Minimum volume
  - Maximum volume
  - Maximum casting volume
  - Line out volume
  - Loudness
  - Do Not Disturb
  - EQ bypass
  - Line out EQ bypass
  - Ducking

## HACS Installation

1. Open HACS.
2. Go to **Integrations**.
3. Open the three-dot menu and choose **Custom repositories**.
4. Add this repository URL.
5. Choose category **Integration**.
6. Install **Crestron DM NAX**.
7. Restart Home Assistant.

## Manual Installation

Copy `custom_components/dm_nax` into your Home Assistant config directory:

```text
/config/custom_components/dm_nax
```

Restart Home Assistant.

## Setup

1. Go to **Settings** -> **Devices & services**.
2. Choose **Add integration**.
3. Search for **Crestron DM NAX**.
4. Enter:
   - Host or IP address
   - Username
   - Password
   - HTTPS setting
   - SSL verification setting
   - Polling interval

Most DM NAX devices use a self-signed certificate, so SSL verification is usually left disabled.

## Notes

The integration uses the `ZoneOutputs`, `InputSources`, and `AvMatrixRouting` objects on current DM NAX firmware. Older object names such as `InputChannels` and `OutputChannels` are kept as fallbacks.

Optional zone tuning entities are disabled by default because they are configuration-style controls rather than everyday dashboard controls.

