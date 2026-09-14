# Changelog

## 0.4.0b3 (Prerelease)

- Adds an enabled Source select for each output with reported matrix routing and
  available inputs, visible directly on the Home Assistant device page.
- Retains NAX-configured names for analog/digital inputs, internal players and
  AES67. Shares label disambiguation and routing with the existing media player.
- Keeps existing media-player and AES67 Stream entity IDs and behavior. Source
  selection does not change volume, mute, receiver streams, or transmit settings.
- Refreshes source feedback after rejected commands as well as accepted commands;
  does not optimistically replace the reported selected source.
- Tests real entity registration, scoped writes, polled feedback, late discovery,
  source-name changes, duplicate labels and unavailable/unknown input handling.
- Clarifies Source versus AES67 Stream versus physical output controls in docs.

## 0.4.0b2 (Prerelease)

- Adds an encoder-IP-to-name example and explains friendly AES67 aliases directly
  in the Home Assistant options dialog, including which dropdown they affect.
- Explains what optional Media Player 2 does, its separate credentials and setup,
  and the distinction between player controls and zone routing.
- Adds step-by-step alias and MP2 configuration guides and links from the dialog
  and README. Warns that changing device player mode reboots the NAX.
- Corrects custom-chime upload guidance based on read-only hardware inspection:
  no supported upload workflow was found on the tested DM-NAX-8ZSA firmware.
- Tests the displayed alias example and English translation consistency.
- No playback, routing, authentication, or device-mode behavior changes. MP2
  remains experimental and requires physical-device validation.

## 0.4.0b1 (Prerelease)

- Adds local AES67 aliases, capability-detected stream/signal/amplifier-fault
  sensors, and allowlisted diagnostics without raw configuration or credentials.
- Adds playback buttons for configured default/custom chimes and recorded
  announcements, preserving hardware-configured destinations and levels.
- Adds optional DuckerConfig timing, attenuation, threshold, bypass/active,
  reference-input and gain controls. Advanced controls are disabled by default.
- Adds an opt-in NVX-to-NAX audio-follow blueprint with independent-music protection.
- Adds experimental Media Player 2 play/pause, track information, authenticated
  provider browsing and signed-content playback on separate streaming entities.
  Requires MP2 mode and separate client credentials; disabled by default.
- Keeps mode changes, reboot, account registration, file upload, arbitrary-URL
  playback and dynamic TTS out of scope. No live routing changes are made by setup.
- Existing 0.3.0 AES67 switching is now confirmed working by the user. New media,
  chime and ducking command workflows still require hardware validation.

## 0.3.0

- Adds a separate enabled AES67 Stream select for each independent output
  exposing a valid `NaxRxStream` reference. Uses the device's actual receiver
  mapping, not a guessed zone-to-stream number.
- Discovers network audio streams through `NaxAudio.NaxSdp`, using session
  names, advertised source IPs, duplicate-name disambiguation and multicast/port validation.
- Configures only the selected receive stream and verifies its reported
  address, port and started status. Serializes commands per receiver and
  bounds each running selection to 15 seconds.
- Adds receiver-only Off and receive-status feedback. Refreshes after partial
  failures rather than optimistically claiming the requested stream is active.
- Preserves volume, mute, matrix source selection, other receivers, transmitter
  settings and encryption settings. Select AES67 as the zone's main source
  separately to hear its network stream.
- Adds regression coverage for real HA select registration, discovery,
  mapping, failures, scope and receive readback. Live end-to-end audio testing
  of the new controls is still required after installation.

## 0.2.7

- Fixes the current-HA Options crash, validates 5-300 second polling intervals,
  and reloads automatically when options change.
- Adds credential repair and connection reconfiguration with device-identity
  checks. Distinguishes connection failures from authentication failures.
- Bounds individual network requests to 10 seconds, serializes authentication
  and writes, retries expired sessions once, and releases managed sessions
  without closing HA's shared connector.
- Corrects channel-family discovery and write paths, including AmpOutput, and
  suppresses read-only channel mute-level controls.
- Uses reported speaker power maxima and basic audio ranges.
- Limits the visibility migration to direct common controls and runs it once,
  preserving user choices and advanced PEQ defaults.
- Tracks capability changes after setup, discovers newly supported controls,
  and rejects writes to controls no longer applicable.
- Reports unsupported and restart-required Crestron action results explicitly.
- Gives duplicate source names unique labels and avoids source writes without
  a reported route.
- Reduces volume optimism from 30 to 2 seconds, honors new device feedback and
  configured limits, and protects rapid-command feedback from older completions.
- Includes original bundled brand icons for HACS/HA and regression tests.
- Preserves zone renaming and existing entity IDs. Fully restart HA after update.

## 0.2.6

- Adds enabled configuration text entities such as `Zone2 Name` for renaming
  physical NAX zones from Home Assistant or `text.set_value` automations.
- Writes only the zone's `Name` property and refreshes device state. Existing
  entity IDs stay unchanged; device-provided display names follow the next poll.
- Validates names as 1-50 characters, with no leading dash, blank-only name, or
  line breaks. Casting names and HA user-assigned display names are separate.
- Treats Crestron's unsupported-property status as a command error.
- Adds registration, identity, payload, validation, rejection and timeout tests.
- Fully restart Home Assistant after updating to load the new text platform.

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
