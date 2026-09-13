# Crestron DM NAX for Home Assistant

Custom Home Assistant integration for Crestron DM NAX devices using the documented CresNext HTTPS API.

## Features

- UI config flow with host, username, password, HTTPS, certificate verification, and polling interval.
- Authenticates through `/userlogin.html` and keeps the device cookies/XSRF token in an integration-scoped session.
- Polls:
  - `/Device/DeviceInfo`
  - `/Device/InputChannels`
  - `/Device/OutputChannels`
  - `/Device/AvMatrixRouting`
  - `/Device/AudioRanges`
- Creates one `media_player` entity per output channel.
- Supports volume, mute, and source selection through narrow partial CresNext POST payloads.
- Adds enabled configuration text entities such as `Zone2 Name` for device-side
  zone renaming using `text.set_value`; existing entity IDs remain stable.
- Adds common zone controls for bass, treble, balance, delay, loudness, DND,
  EQ bypass, stereo, tone profile, and night mode, with deeper calibration
  controls available as disabled entities.
- AES67 stream selection with receive verification and optional friendly aliases.
- Capability-detected signal/fault sensors and privacy-preserving diagnostics.
- Configured chime/recorded-announcement playback and advanced DuckerConfig controls.
- Optional experimental Media Player 2 playback, track metadata and signed-content browsing.

## Notes

Most DM NAX devices use self-signed certificates unless a trusted certificate has been installed. Leave certificate verification disabled for the common default device setup.

Zone controls use local polling. Optional Media Player 2 telemetry uses WebSockets
and separate client credentials. The integration never changes device mode or
registers music accounts. See the [setup guide](https://github.com/Phant0mElit3/ha-dm-nax/blob/main/docs/MEDIA_AND_AUTOMATION.md)
for prerequisites and prerelease limitations.
