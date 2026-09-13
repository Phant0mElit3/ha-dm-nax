# Media, Announcements and Automation

## Prerelease Installation

0.4.0b1 is an opt-in prerelease. In HACS, open the NAX repository's download/version
dialog and enable prerelease versions if needed, then select 0.4.0b1 and restart
Home Assistant. Stable 0.3.0 remains available. Existing zone entities and their
identifiers are retained. No device mode, music account, volume, mute, routing,
or automatic audio-follow settings are changed during installation.

The new protocol is tested against a local WebSocket server, not yet a physical
Media Player 2 installation. Model/firmware capability differences still require
hardware validation. The existing NVX video and NAX AES67 route changes have been
confirmed working by the user on the previously documented setup.

## Friendly AES67 Names

Open NAX **Configure** and enter a mapping under **AES67 source IP to friendly
name**, for example:

```json
{"192.0.2.10": "Apple TV", "192.0.2.11": "Cable"}
```

Use the encoder's advertised source IP, not its multicast address. The dropdown
will show `Apple TV [192.0.2.10]`. Names are local to HA; stream session names on
the hardware are unchanged. Duplicate feeds remain disambiguated. Automations
that select an option by its full label must be updated when an alias changes.

## Diagnostics

The NAX device exposes diagnostic entities when their underlying fields exist:
AES67 receive status, error code, format, sample rate and channel count; audio
signal and clipping; amplifier critical, DC, voltage, temperature, current and
clipping faults. Missing properties are not represented as healthy/zero values.

Download integration diagnostics through the entry menu. The report includes
capability information and counts, not raw device responses, credentials, IP
addresses, serial numbers, friendly zone names, music accounts or signed content.
Receive-started status does not itself prove audible sound.

## Chimes and Recorded Announcements

Configure default/custom chimes, recordings, playback zones, repetition and
duration in the **NAX web interface** first. A **Chime <name>** button appears in
HA for each reported playable slot. Press it or call `button.press` from an
automation. Playback uses the destinations already configured on that slot,
which can include multiple rooms. Its HA attributes list reported playback zones.

For spoken announcements, upload/configure a recording as a custom chime using
the NAX web interface. This release does not upload files, accept arbitrary URLs,
implement dynamic TTS, or emulate announcement mixing by replacing a music source.
The REST API recommends using the web interface for chime configuration; HA sends
only the documented `Play` trigger and refreshes feedback. Acceptance of that
trigger is not proof that each target speaker emitted sound.

Existing per-zone **Announcement Volume**, **Announcement Ducking Level**, and
**Announcement Ramp Time** entities control the device's announcement behavior.
They may need to be enabled under the device's disabled entities. Normal zone
volume and mute are not rewritten by chime playback. Check Do Not Disturb and the
slot's target zones when testing, and begin at a conservative announcement level.

## Ducking

There are distinct mechanisms; enabling one does not enable all of them:

- **Zone Ducking / Ducked Volume:** existing zone controls, including the
  device's connected-speaker/voice-service behavior. An enabled flag is not a
  general-purpose command to duck whatever is playing immediately.
- **Announcement Ducking Level / Ramp Time:** device-managed attenuation and
  transition timing when a chime/intercom interrupts audio.
- **DuckerConfig**, only on devices exposing it: bypass, active state, attack,
  release, hold, threshold, attenuation, per-input reference enable and gain.

Advanced DuckerConfig entities are disabled by default. Their names retain
the device's actual output/input IDs; the integration does not guess which zone
they correspond to. Verify the mapping in the device UI before enabling them.
Timing and gain units are converted for HA: attack in milliseconds, hold in
seconds, release in milliseconds, and attenuation/reference gain in dB.
Writes affect only the selected field. Nothing changes when these entities are
discovered or enabled in the HA registry.

## Optional Audio Follows Video

Import [the audio-follow blueprint](../blueprints/automation/nvx_nax_audio_follow.yaml)
into HA. Create an `input_boolean` helper as its enable toggle and select the
correct NVX video selector, NAX zone and AES67 stream selector. Provide an explicit
mapping of exact NVX source option labels to encoder source IPs.

By default, it follows source changes only while the zone's main input is already
AES67. Switching the zone to music from another input prevents takeover. The
optional takeover setting allows it to select AES67 after the stream command is
confirmed. It never changes volume or mute. Unavailable, unknown, Off, stale,
unmapped and ambiguous selections are skipped. Turning on the helper does not
immediately route; the next valid NVX source change triggers it. Importing the
blueprint does not create or enable an automation.

## Optional Media Player 2

Do not enable this simply to listen to NVX AES67 audio. It is for the NAX's own
streaming music players, and requires the device to run **Media Player 2**.

Review [Crestron's MP2 setup guide](https://sdkcon78221.crestron.com/sdk/Media-Player-API/Content/Topics/Quick-Start/Make-API-Calls.htm)
before making changes. Checking the current mode is read-only; switching modes
reboots the device and can affect existing music workflows. Create a dedicated
client using the documented device console procedure. The resulting UUID and
secret are **not** the web UI username/password. The integration does not switch
modes, reboot, create clients, or register music-service accounts.

Enter that client UUID and secret in NAX **Configure**, and enable the experimental
Media Player 2 option. HTTPS must already be enabled. The existing certificate
verification preference is retained. Leave the secret blank on subsequent option
edits to retain it; it is excluded from diagnostics.

When connected, separate **Streaming PlayerXX** media players appear. These are
streaming engines rather than zones: multiple rooms may be listening to the same
engine. Choose the corresponding input using the zone's existing Source control.
Playback commands do not route a zone or select a different amplifier input.

Supported operations:

- Play/pause when the current player/provider advertises those actions.
- Reported track/station title, artist, album and duration.
- Browse authenticated, non-zone-based music providers already configured on
  the NAX, with paginated directories and playback of signed browsed content.
- WebSocket player telemetry, reconnect attempts, bounded commands and readback.

Spotify Connect and AirPlay are not browsable catalogs here. Their source apps
remain responsible for browsing/casting. Whether their play/pause and metadata
are available depends on what the device reports for that player. Browser items
expire on reconnect; reopen the browser to get fresh signed references. The
integration neither edits signed objects nor exposes them as entity attributes.

Not included: music-account registration, queues, search, arbitrary URL playback,
TTS/announcement mixing, or playback control of an external NVX source. A failed
MP2 connection does not disable the existing zone-routing connection.

## References

- [DoorChimes](https://sdkcon78221.crestron.com/sdk/DM_NAX_REST_API/Content/Topics/Objects-NAX/DoorChimes.htm)
- [ZoneOutputs and announcement controls](https://sdkcon78221.crestron.com/sdk/DM_NAX_REST_API/Content/Topics/Objects-NAX/ZoneOutputs.htm)
- [DuckerConfig](https://sdkcon78221.crestron.com/sdk/DM_NAX_REST_API/Content/Topics/Objects/DuckerConfig.htm)
- [MP2 registration](https://sdkcon78221.crestron.com/sdk/Media-Player-API/Content/Topics/API-Reference/Register-Client-API.htm)
- [MP2 playback](https://sdkcon78221.crestron.com/sdk/Media-Player-API/Content/Topics/API-Reference/Playback-API.htm)
- [MP2 browsing](https://sdkcon78221.crestron.com/sdk/Media-Player-API/Content/Topics/API-Reference/Browse-API.htm)
