# Changelog

## 0.2.5

- Fixes zone number, switch, and select entities failing to register with
  `AttributeError: ... entity_registry_visible_default` by inheriting Home
  Assistant's platform entity descriptions.
- Preserves existing entity IDs, common-control visibility, and disabled defaults
  for advanced controls.
- Adds regression tests using Home Assistant 2026.9.2 entity registration and
  state writing, run automatically on pushes and pull requests.
- After updating in HACS, fully restart Home Assistant to load the corrected code.

## 0.2.4

- Adds setup logging for zone number, switch, and select entity creation counts.
- Uses explicit entity lists during platform setup to make registration behavior
  easier to diagnose in Home Assistant logs.

## 0.2.3

- Moves common zone controls out of Home Assistant's configuration entity
  category so they appear with normal device controls.
- Keeps advanced tuning and calibration controls as disabled configuration
  entities.

## 0.2.2

- Automatically re-enables common zone controls that were registered as
  disabled by version 0.2.0, so existing installs see the new controls after
  updating and restarting Home Assistant.

## 0.2.1

- Enables common zone controls by default so they are visible after install:
  bass, treble, balance, delay, sub trim, line out volume, loudness, Do Not
  Disturb, EQ bypass, line out EQ bypass, ducking, stereo, CSS, tone profile,
  and night mode.
- Keeps deeper calibration, announcement/intercom, speaker configuration,
  provider, test tone, identify, and PEQ entities disabled by default.

## 0.2.0

- Adds disabled-by-default optional zone controls for deeper DM NAX settings:
  announcement/intercom levels, ducked/mute volume, ramp times, test tone,
  crossover, sub trim, speaker output/protect/power, AirPlay and Spotify zone
  provider toggles, night mode, tone profile, speaker impedance, zone
  configuration, and PEQ band controls.
- Adds nested ZoneOutputs partial POST support for ZoneAudio and zone-level
  settings.

## 0.1.0

- Initial HACS-ready custom repository package.
- Adds UI config flow for Crestron DM NAX devices.
- Adds local polling of device info, input sources, zone outputs, audio ranges,
  and AV matrix routing.
- Adds one Home Assistant `media_player` entity per zone.
- Supports zone volume, mute, and source selection.
- Adds optimistic volume state for smoother Home Assistant slider feedback.
- Adds optional disabled-by-default zone number and switch controls for common
  ZoneAudio settings.
- Validated live against a DM-NAX-8ZSA.
