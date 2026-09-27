---
status: accepted
---

# Automations listen only to the Devices their Triggers name

Until Automations, the Engine watched nothing: a Device's state was read only when a Client asked, and Offline came only from Scans. A Trigger such as "when the plug turns on" or "when Bulb 1 goes Offline" needs the Engine to notice changes nobody asked about, including ones made by a wall switch, the Smart Life app or another person. We decided the Engine listens **only to the Devices named in a state or Offline Trigger of an enabled Automation** (a Group's members when the Trigger names a Group), and to nothing when no such Automation exists. That keeps Control light on the PC (roadmap step 8) for everyone who doesn't use these Triggers.

## Decisions

- **Push first.** Every brand with a real state can tell us about changes over a connection it keeps open: Yeelight's notifications on its TCP connection, Tuya's status messages on its socket, the Android TV Remote connection a Streamer already holds. A brand without push is read on an interval, only while it is listened to. Infrared Remote Devices are never listened to: their Assumed State changes only when Control sends a Signal, so the Engine already knows.
- **Listening follows the Automations.** Enabling, editing, disabling or deleting an Automation (or changing a Group's members) starts and stops listening at once. Conditions don't listen: they read a Device once, when a Trigger fires.
- **Offline after a minute.** A listened-to Device whose connection drops is reconnected quietly; if it still hasn't answered after 1 minute it becomes Offline (on Home too, and "goes Offline" Triggers fire). Any answer, a reconnect, a Scan or a command, brings it back online. So Offline now also means "stopped answering while listened to", not only "missing from the latest Scan".
- **Changes made by Control count.** A change an Automation or a person makes through Control fires Triggers the same way as one pushed by the Device, so "when the TV turns on" works whoever turned it on (the loop guard is in [ADR 0012](0012-how-an-automation-run-behaves.md)).

## How each brand listens (decided when it was built, 2026-09-27)

- **Yeelight**: its own TCP connection to the bulb, with TCP keep-alive, reading the "props" notifications a bulb sends on every open connection. One request per (re)connection, for the first reading; the keep-alive notices a bulb that lost power without spending its rate-limited requests.
- **Tuya**: the plug's one local connection, kept open with its heartbeat; the plug pushes its status when the relay changes. While listened to, Control's own commands and reads for the plug go over that connection.
- **Android TV**: the Remote connection a Streamer already holds; the device pings it every 5 s, so a lost one is noticed. While it's lost, the address is read again from the Registry, so a box a Scan found at a new address is reconnected there (Yeelight and Tuya do the same on each reconnection).
- Only changes fire: the first reading after listening starts fires nothing, and "stays so for N min" counts from then (nothing is kept across a restart). A Streamer's screensaver doesn't count as leaving its app.
- Offline Triggers are for Devices with a connection of their own (lights, plugs, Streamers), not Remote Devices or Hubs.

## Considered options

- **Poll every Device on an interval**: simple, but costs CPU and network all day, is slow to notice, and Yeelight bulbs rate-limit requests.
- **Listen to everything always** (which would also give Home live Tiles): the most capable, but holds a connection to every Device for users with no Automations at all. Live Tiles can come later as their own decision.
- **Only notice changes Control makes**: free, but misses wall switches, other apps and the physical remote, which is most of what people want to react to.
- **Mark Offline as soon as the connection drops**: faster, but every Wi-Fi blip would fire Offline Triggers.

## Consequences

- A Device named by an Automation's Trigger holds one open connection to the Engine. Commands to it should reuse that connection where the brand allows, so Yeelight's rate limit isn't hit twice.
- Offline can now change between Scans, so Home may show a Device going Offline without anyone scanning.
