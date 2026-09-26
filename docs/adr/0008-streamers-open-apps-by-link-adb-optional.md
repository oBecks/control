---
status: accepted
---

# Streamers open apps by link, with adb as an optional second step of the Link

Android TV boxes are controlled over the Android TV Remote protocol (`androidtvremote2`): a Link with a PIN, then power, keys, the open app and volume. Its only way to open an app is to send a link. Opening by package name (`market://launch?id=…`) used to go through the Play Store, but that route broke. On the user's NVIDIA Shield and yes+ box it, `intent:` and `android-app://` links are all refused. So each Streamer App Shortcut keeps the app's package (to name the open app) and, when known, a link that opens it (`https://www.youtube.com`, `stremio://`).

Some apps declare no link at all. yes+ (`il.co.yes.yesplus`) has only a home-screen entry. For those, Control has two ways, chosen in this order:

1. **adb, when the Streamer allows it.** An optional second step of the Link: the user turns on the box's developer mode (Network debugging) and presses Allow on the TV once. Control then opens any app directly (`monkey -p <package>`) and can list what's installed, so the app picker shows the box's real apps instead of Control's catalogue. Control has one adb key for every box; its private half is sealed by `vault`, like the Android TV client key (`%LOCALAPPDATA%\Control\androidtv\`). Library: `adb-shell`.
2. **Otherwise, the Play Store page.** Control opens the app's store page (`market://details?id=…`), waits until the Play Store is in front, and presses OK: on an installed app the focused button is Open. It takes about two seconds longer and is checked afterwards.

Links still come first when an app has one, since they need neither.

## Consequences

- Nobody needs developer mode: every Streamer works with just the PIN Link. adb is offered at setup and when an app without a link is added, never required.
- A box with developer mode on accepts adb from any computer the user allows on the TV. Control only asks for what it uses: the installed list and opening apps.
- The Play Store route presses OK on whatever is focused. On an app that isn't installed that's Install, which would install it. The user adds only apps they have, so this is accepted.
- If debugging is turned off later, opening an app falls back to the Play Store route. The installed list says why it can't be read.

## Considered options

- **adb only, required at setup**: exact, but developer mode is too much to ask of everyone.
- **Play Store route only**: no setup, but slower, less certain, and no installed list.
- **Guessing links per app**: yes+ declares none, so there is nothing to guess.
