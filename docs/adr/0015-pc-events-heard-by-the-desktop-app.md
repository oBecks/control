---
status: accepted
---

# PC events are heard by the Desktop App, and the Engine starts the Runs

Roadmap step 5, phase 2, asked for Triggers on the PC itself: it wakes, you log in, Control starts. Asked for 2026-09-29, with the opposites (locked, going to sleep, shutting down) added in the same round.

## Decisions

- **One Trigger kind, `pc`, with an event:** `starts` (Control starts), `wakes`, `unlocks` (you unlock the PC, or sign in or come back to this session), `locks`, `sleeps` and `shuts_down` (the PC shuts down, or you sign out). Conditions are checked as for any Trigger; a Run by one of these is a normal Run.
- **Control starts is the Engine's own** (`Runner.start`): it fires whenever the Engine starts, with Windows if Start with Windows is on, or whenever the user starts it. It needs no Windows hook, works for `control serve` too, and is not accepted from outside.
- **The rest are heard by the Desktop App**, which already runs on the user's desktop session (the Engine may run without a desktop one day, on an always-on box). `desktop/events.py` owns a top-level window that is never shown, since Windows sends power broadcasts (`WM_POWERBROADCAST`) and shutdown messages (`WM_ENDSESSION`) only to those, and registers it for session changes (`WTSRegisterSessionNotification`, for lock and unlock). It sleeps in its message loop and costs nothing while nothing happens (roadmap step 8). It tells the Engine through `POST /api/pc-events`, open to the PC itself only, the way the Hotkey listener and the notices watch do. Wake is `PBT_APMRESUMEAUTOMATIC`, which Windows sends for every wake, whoever woke the PC. A repeat of the same event within a few seconds (30 for a wake) is told once.
- **Only live, nothing caught up** (as with Devices, ADR 0011): an event while Control wasn't running isn't logged as missed and doesn't fire on the next start, other than Control starting itself.
- **Going to sleep and shutting down get only a moment.** The Desktop App holds Windows for up to 2.5 s for the Runs to end (the Engine holds its answer that long), so quick Actions such as a notice or a command to a light get through; a Wait doesn't, and a Run still going when the PC sleeps is abandoned as interrupted on wake, like any Run the PC slept through (ADR 0012). At shutdown Control itself stops as Windows ends the session, which interrupts the rest. The Trigger's editor and the Assistant's tool say so.
- **Just after Control starts at sign-in, Devices may not answer yet** (the Wi-Fi is still coming up). A failed Action is reported like any other; no waiting or retrying is built in. The Automation can start with a Wait.
- **No loop guard is needed:** nothing an Automation does changes the PC's state.

## Considered options

- **Detecting a wake in the Engine** (the wall clock jumped further than the awake clock, which the Runner and listening already compare): needs no window, but can't say the PC is going to sleep, or was locked, and finds out up to 5 minutes late.
- **A Windows service or scheduled task** for the events: heavier, needs elevation or a task per user, and the Desktop App already has a session.
- **`RegisterPowerSettingNotification`** (console display on/off): says the screen turned off, not that the PC slept.
- **A message-only window**: gets no broadcasts, so it never hears a sleep or a wake.
