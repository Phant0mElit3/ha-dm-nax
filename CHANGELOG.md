# Changelog

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

