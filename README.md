# Crestron DM NAX for Home Assistant

Local polling Home Assistant integration for Crestron DM NAX audio devices using
the local CresNext REST API.

This project is early and was built against a live DM NAX device. Use it as a
custom HACS repository until more models and firmware versions have been tested.

Tested live against a `DM-NAX-8ZSA` running firmware `3.2.0121.01081`.

## Installation With HACS

1. In Home Assistant, open HACS.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add this repository URL:

   ```text
   https://github.com/Phant0mElit3/ha-dm-nax
   ```

4. Select category **Integration**.
5. Install **Crestron DM NAX**.
6. Restart Home Assistant.
7. Add the integration from **Settings > Devices & services**.

## Manual Installation

Copy `custom_components/dm_nax` into your Home Assistant config folder:

```text
/config/custom_components/dm_nax
```

Then restart Home Assistant.

## Configuration

The integration supports UI setup from **Settings > Devices & services**.

You will need:

- DM NAX host or IP address
- Web UI username
- Web UI password
- HTTPS setting
- SSL verification setting
- Polling interval

Most DM NAX devices use a self-signed certificate, so SSL verification is
usually left disabled.

Polling intervals are limited to 5-300 seconds. Changes in **Options** reload
the integration automatically. Use **Reconfigure** to change the host or
connection settings; the replacement connection must identify the same device.
Expired credentials can be repaired through Home Assistant's reauthentication
flow without deleting the integration or its entities.

## Current Coverage

- Device metadata from `/Device/DeviceInfo`
- Input source discovery from `/Device/InputSources`
- Zone discovery and state from `/Device/ZoneOutputs`
- Audio ranges from `/Device/AudioRanges`
- Source routing from `/Device/AvMatrixRouting`
- Zone media players with volume, mute, source list, and source select
- Zone name text entities, enabled under the device's configuration controls
- Optimistic Home Assistant volume state after accepted volume commands
- Common zone configuration entities enabled by default:
  - Bass
  - Treble
  - Balance
  - Delay
  - Sub trim
  - Line out volume
  - Loudness
  - Do Not Disturb
  - EQ bypass
  - Line out EQ bypass
  - Ducking
  - Stereo
  - CSS
  - Night mode
  - Tone profile
- Advanced zone configuration entities disabled by default:
  - Default volume
  - Minimum volume
  - Maximum volume
  - Maximum casting volume
  - Ducking and mute volume levels
  - Volume ramp up/down times
  - Test tone and test tone volume
  - Crossover frequency
  - Speaker output, speaker protect, speaker power, and impedance
  - Announcement and intercom volume/ducking/ramp controls
  - AirPlay and Spotify Connect zone provider toggles
  - Zone configuration
  - PEQ band frequency, gain, bandwidth, type, and bypass

## Renaming Zones

Open the DM NAX device in **Settings > Devices & services** and edit the
configuration text entity for the physical zone, for example **Zone2 Name**.
This changes the name stored on the NAX. Names must be 1-50 characters, cannot
start with a dash, and cannot be blank or contain line breaks.

Automations can use the standard `text.set_value` action. Replace the example
entity ID below with the Zone2 Name text entity from your installation:

```yaml
action: text.set_value
target:
  entity_id: text.crestron_dm_nax_zone2_name
data:
  value: Kitchen
```

The zone's device-provided display names update after polling. Existing entity
IDs stay unchanged, so dashboards and automations keep their references. Names
you have explicitly overridden in HA stay overridden. AirPlay/Spotify casting
names are separate device settings and are not changed by this action.

Fully restart Home Assistant after installing an integration update.

## Known Notes

- The integration targets current DM NAX firmware objects: `ZoneOutputs`,
  `InputSources`, and `AvMatrixRouting`.
- Alternate `InputChannels` and `OutputChannels` devices use their own write
  schema, including `AmpOutput`. Their read-only mute level is not offered as a
  writable control. This path has automated tests but still needs live model
  verification; it is not simply an older name for the zone-based API.
- Common zone tuning entities are enabled by default; advanced entities are
  disabled by default because they are configuration-style controls rather than
  everyday dashboard controls.
- Speaker, zone configuration, provider, and PEQ entities are disabled by
  default because they can materially change how a zone behaves.
- Controls follow current capabilities. Unsupported controls become unavailable
  and newly supported controls are discovered on refresh. Crossover requires an
  independent zone in a supported 2.1 bridge mode.
- Speaker power uses the device's reported maximum, including 300/500 W where
  supported. Reported basic audio ranges are used when provided.
- Duplicate source names include an input identifier so each source remains
  selectable. Source selection is offered only when the device reports a route.
- Accepted volume changes are displayed for at most two seconds while settling;
  new device volume feedback takes precedence. Device minimum/maximum limits
  are respected. A dashboard slider's drag/release behavior is still controlled
  by the dashboard card, not by the integration.
- Crestron restart-required responses are reported explicitly; the integration
  does not reboot the device automatically.
- The visibility migration runs once and no longer enables individual PEQ bypass
  controls. Previously enabled entities are preserved, including those enabled
  by the older bug; disable unwanted PEQ entities manually in HA.
- Bundled original brand icons display on Home Assistant 2026.3 and newer.
  See [HA brand-image documentation](https://developers.home-assistant.io/docs/core/integration/brand_images/).
- This maintenance release does not add fault/signal sensor entities, input
  controls, push updates, chime playback, or unverified advanced ducking controls.

## Testing

The regression suite runs against Home Assistant 2026.9.2 and Python 3.14:

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Tests exercise real HA entity registration as well as simulated API responses,
configuration flows, capability changes, routing, and volume reconciliation.
They do not make changes to a physical NAX.

## Crestron API

DM NAX REST API quick start:

https://sdkcon78221.crestron.com/sdk/DM_NAX_REST_API/Content/Topics/Quick-Start-2.htm

## Trademark Notice

This project is an independent Home Assistant custom integration and is not
affiliated with, endorsed by, sponsored by, or supported by Crestron Electronics,
Inc.

Crestron, DM NAX, and related names, marks, logos, and images are the property
of Crestron Electronics, Inc. The MIT license applies to the original
integration source code only and does not grant rights to Crestron trademarks,
logos, images, or other third-party assets.

See [NOTICE](NOTICE) for the trademark notice.
