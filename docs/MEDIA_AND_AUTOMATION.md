# Media, Announcements and Automation

## Prerelease Installation

0.4.0b3 is an opt-in prerelease. In HACS, open the NAX repository's download/version
dialog and enable prerelease versions if needed, then select 0.4.0b3 and restart
Home Assistant. Stable 0.3.0 remains available. Existing zone entities and their
identifiers are retained. No device mode, music account, volume, mute, routing,
or automatic audio-follow settings are changed during installation.

The new protocol is tested against a local WebSocket server, not yet a physical
Media Player 2 installation. Model/firmware capability differences still require
hardware validation. The existing NVX video and NAX AES67 route changes have been
confirmed working by the user on the previously documented setup.

## Source and AES67 Stream Selection

Starting with 0.4.0b3, a **<zone name> Source** dropdown appears directly under
the NAX device's Controls for each output with a reported matrix route and input
list. This exposes the source selection already available inside the zone media
player; neither that control nor the existing AES67 Stream entity is removed.

- **Source** selects a reported NAX input: an analog or digital connection, an
  internal music player, or AES67. Labels use the names configured on the NAX.
- **AES67 Stream** selects the network feed for that zone's AES67 receiver. The
  zone must also have AES67 selected as its Source to hear the feed.

For example, choose a turntable's input name under **Living Room Source** to hear
that analog input. To return to NVX audio, select the desired encoder under
**Living Room AES67 Stream**, then select **AES67** under **Living Room Source**.
Selecting an internal player does not start its playback.

Physical outputs are destinations, not additional local inputs. A network feed
transmitted from an output can appear in AES67 Stream if the NAX discovers it;
the integration does not create routes from guessed output names. Line Out
controls remain attached to the zones that report line-output support.

The two source controls share the same input labels and matrix command. Selection
changes only the reported route, then refreshes device feedback. It does not
change volume, mute, the receiver's saved stream, or transmitter configuration.
No route is changed by installation or entity discovery. Crestron Home or another
controller can still change the same hardware route; HA reflects polled state.

## Friendly AES67 Names

This is an optional Home Assistant display setting, not a hardware rename or a
new stream. It requires 0.4.0b1 or a later version containing stream aliases.

1. Open **Settings > Devices & services > Crestron DM NAX** in Home Assistant.
2. Select **Configure** for the NAX entry, not the NVX integration or the device's
   web interface.
3. Find **AES67 source IP to friendly name**. Replace an empty mapping in that
   field's editor with the example below, using your own encoder IP addresses
   and preferred names. Do not add this to `configuration.yaml`.

```json
{
  "192.0.2.10": "Apple TV",
  "192.0.2.11": "Cable"
}
```

4. Leave Media Player 2 and polling settings unchanged, then select **Submit**.
   The integration reloads automatically; changing aliases does not require a
   Home Assistant restart.
5. Open the NAX device's zone **AES67 Stream** selector. The example produces
   `Apple TV [192.0.2.10]` and `Cable [192.0.2.11]`. The separate zone **Source**
   selector still says **AES67**. Saving names does not switch either selector.

Use the encoder's advertised source IP, not the NAX IP or a multicast address.
Each name must contain 1-60 printable characters. Without a matching alias the
advertised stream name remains visible. Enter an empty object (`{}`) to remove
all aliases. An alias cannot make an undiscovered stream appear. Names apply
to stream selectors within this NAX integration entry, not other integrations.
Duplicate feeds remain disambiguated. Update the mapping if an encoder IP changes,
and update automations that select an option by its full label after renaming.

If the field is missing, check the installed version in HACS. After installing
an updated integration version, restart Home Assistant before opening Configure.

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

Configure the available chimes and their playback zones in the **NAX web
interface** first. Repetition and duration controls depend on firmware. A
**Chime <name>** button appears in
HA for each reported playable slot. Press it or call `button.press` from an
automation. Playback uses the destinations already configured on that slot,
which can include multiple rooms. Its HA attributes list reported playback zones.

Custom-slot playback is supported only when the device reports playable
`CustomChimes` entries; this does not imply support for creating or uploading
recordings. This release does not upload files, accept arbitrary URLs, implement
dynamic TTS, or emulate announcement mixing by replacing a music source.

Read-only hardware inspection on 2026-09-13 of a DM-NAX-8ZSA running
3.2.0121.01081 found 26 built-in chimes and no upload control in the Chimes UI.
`DoorChimes` version 2.0.5 reported only `DefaultChimes`, with `FilterType` set
to `All`; no `CustomChimes` collection was present. `FileMgmnt.FileEntries`
listed only `SpeakerProfiles`, and `FilePaths` exposed a generic file staging
path but no chime-specific path. These observations do not establish a supported
custom-chime upload workflow. Do not upload audio through the speaker-profile
importer or overwrite built-in chime files. Custom recordings need a verified
vendor-supported provisioning method before they can be tested here.

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

MP2 is the device's newer built-in music-player system and control API, not an
audio format or a Home Assistant audio server. With this option enabled, Home
Assistant acts as a remote: it sends player commands and receives player-state
updates over an authenticated local WebSocket connection. The NAX plays the
music; Home Assistant does not relay its audio. Our implementation exposes
play/pause, reported track information, and browsing/playback for supported
providers already configured on the NAX.

Think of two independent controls: a **Streaming PlayerXX** entity controls what
an internal player plays, while a zone's **Source** control decides whether that
room hears that player. If several rooms use the same player, pausing it affects
all of them. NVX AES67 routing is separate: MP2 does not control the external
source feeding an NVX encoder, improve AES67 switching, or add custom-chime uploads.
The Home Assistant checkbox connects to an already prepared MP2 system; it does
not enable MP2 mode on the hardware.

### Prepare the NAX

This feature is experimental and has not yet been verified against a physical
MP2 installation. Do this during a maintenance window: changing player modes
reboots the NAX and may affect existing music/control-system workflows. Confirm
compatibility with any existing controller before changing modes. The integration
does not switch modes, reboot, create clients, or register music-service accounts.

1. Open an SSH console to the NAX, or use **Text Console** in Crestron Toolbox.
   For SSH, replace `YOUR_USERNAME` and `NAX_IP` with the device's authorized
   console login and address: `ssh YOUR_USERNAME@NAX_IP`. Enter the password
   interactively; do not put it in the command. If console access is unavailable,
   resolve that with the device administrator rather than weakening security.
2. At the device prompt, run the read-only command:

   ```text
   mediaplayer
   ```

3. If it reports MP2, skip the mode change. If it reports MP1, run the following
   only when ready for an immediate reboot and audio interruption, then wait for
   the NAX to return, reconnect, and run `mediaplayer` again to confirm MP2:

   ```text
   mediaplayer MP2
   ```

If the firmware does not recognize these commands, stop and verify model/firmware
support with Crestron. A firmware upgrade is not performed by this integration.
These mode commands follow [Crestron's MP2 setup guide](https://sdkcon78221.crestron.com/sdk/Media-Player-API/Content/Topics/Quick-Start/Make-API-Calls.htm).

4. Create a dedicated Home Assistant client once, unless you already have its
   saved credentials:

   ```text
   createclient homeassistant
   ```

5. Keep the returned **UUID** and **Secret** securely. They authorize the client;
   do not post them in issues, screenshots, or logs. Use the complete returned
   Secret, including any trailing `=`. Do not generate a replacement UUID or
   encode the Secret again. They are separate from the web UI username/password.
   See [Crestron's client authentication commands](https://sdkcon78221.crestron.com/sdk/Media-Player-API/Content/Topics/Quick-Start/Client-Authentication-Commands.htm).

### Enter the Home Assistant Options

1. Open **Settings > Devices & services > Crestron DM NAX**.
2. The entry must already use **Use HTTPS**. If it does not, use the entry's
   **Reconfigure** action to update the connection, first confirming HTTPS works
   on the NAX. Keep the existing certificate-verification policy; MP2 uses it too.
3. Select **Configure** and fill in the following fields:

   | Field | Value |
   | --- | --- |
   | Enable Media Player 2 (experimental) | On, after confirming device MP2 mode |
   | Media Player 2 client UUID | UUID returned by `createclient` |
   | Media Player 2 client secret | Secret returned by `createclient` |
   | AES67 source IP to friendly name | Leave existing aliases unchanged |
   | Polling interval in seconds | Leave existing value unchanged |

4. Select **Submit**. The integration reloads and attempts the separate MP2
   connection. Saving options validates credential format, not successful device
   authentication. No Postman setup or manual authorization-header script is
   needed; the integration handles signing and WebSocket registration.
5. On later edits, a blank secret field retains the stored secret. To stop using
   MP2, turn off its enable option; this does not revoke credentials or change
   the device's player mode.

### Verify Playback

Open the NAX device in Home Assistant and look for **Streaming PlayerXX** entities.
Confirm that one becomes available. Music-service accounts must already be
configured on the NAX using the vendor-supported setup for that provider. Start
with an existing working service, then check metadata and available play/pause
controls before testing media browsing. Browser contents depend on the provider.

If players are missing or unavailable, verify device MP2 mode, HTTPS connectivity
from Home Assistant, and the dedicated UUID/Secret pair. Review Home Assistant's
DM NAX logs without sharing secrets. Saving the form alone does not prove MP2
works; this hardware validation is still pending on our test installation.

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
