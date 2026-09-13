# Changelog

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
