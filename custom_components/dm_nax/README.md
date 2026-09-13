# Crestron DM NAX for Home Assistant

Custom Home Assistant integration for Crestron DM NAX devices using the documented CresNext HTTPS API.

## MVP features

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

## Notes

Most DM NAX devices use self-signed certificates unless a trusted certificate has been installed. Leave certificate verification disabled for the common default device setup.

The integration currently uses local polling. The DM NAX API also exposes long-poll and WebSocket update paths, which are good next steps once the basic output/channel mapping is verified against real device payloads.

