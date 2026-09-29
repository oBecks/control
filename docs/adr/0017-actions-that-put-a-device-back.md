---
status: accepted
---

# Actions that put a Device back

Roadmap step 5, phase 2: "undo after / while": turn the porch light on and have it go back to how it was after 10 minutes, or keep the fan on only while it's hot.

## Decisions

- **An option on a control Action, not a separate step.** A toggle, set or step on one Device (a Group can't: putting a merged reading back would flatten its members; a Device with only a Power Toggle can't: Control can't tell how it was) may carry `"undo": {"after": minutes}` (1 to 1440) or `{"while": true}`. A press, an app opening, a Scene, a Wait, a Notify or a run can't be put back. Words: "Turn on Porch, then put it back after 10 min".
- **"How it was" is a Scene part.** Just before the Action, Control reads the Device and captures it as a Scene does (`scenes.capture`: on or off and, while on, brightness, colour or white, an AC's mode, temperature and fan). After the Action it reads and captures again: how the Action *left* it. Putting back sends the first with the Scene machinery (`scenes_api._send`).
- **Only if it's still as the Action left it.** At put-back time the Device is read and compared with how the Action left it (`scenes.matches`, with its slack for rounding). If it isn't, someone used it meanwhile (the app, a physical remote we heard of, another Automation), and it is **left alone**: the Run's step says "Left as it is: it had been changed since". An Action that changed nothing (it was already so) is "Nothing to put back".
- **Kept in the Registry** (`undos`: the Run and step, the Device, how it was, how it was left, when it's due), so a wait of hours survives Control quitting and the PC sleeping. The Runner's scheduler looks at them like timed Triggers: at the due time, or, for "while", at most every 60 s, since that reads Devices. Unlike an Action late from a Wait (ADR 0012), a put-back that was missed while the PC was off is done when Control is next running: the comparison above protects what someone set since, and the point is to end in the state it began in.
- **"While" follows the Automation's Only if.** It needs Conditions. Once they're known not to hold any more (all of them, or, with "any", none of them), the Device is put back. A Condition that can't be told (a Device that doesn't answer, someone whose phone isn't found yet) is not "stopped": nothing happens until it can. A Run by hand skips the Only if, so with "while" it may be put back at the next look if the Conditions don't hold.
- **A new Run for the same Automation and Device replaces a waiting one but keeps the original "how it was"**: the new Run found the Device as the old one left it, and putting it back to that would never end where it began. The wait starts again.
- **A failed put-back is retried every 30 s, five times**, then dropped with a notice. A Device or Automation that was removed drops its put-back (deleting an Automation deletes its waiting ones).
- **Its own change never triggers it** (`listening.acting`, ADR 0011), like any Action of the Automation's.
- **Where it shows:** the Then editor's "Afterwards" choice, the Action's words, and, on each Run's step, what became of it (`step["undo"]`, added to the step after the Run ends). Assistant: `undo_after_minutes` and `undo_while` on an Action.

## Considered options

- **A separate "Undo the above after N min" Action:** reverts every earlier Action at once; more general, but harder to read and to check, and half the Actions can't be put back.
- **Restoring "off"/"on" only:** simpler, but a light that was at 30% warm white would come back at 100%.
- **Always putting back:** would fight whoever turned the light off from the app in the meantime.
- **Listening to the Conditions for "while"** (push, like Device Triggers): exact, but would hold a connection open for every Device named in a Condition for as long as anything waits. A look every minute costs little and only runs while something waits.
- **Keeping it in the Run's thread** (a long Wait): a Run would stay "running" for hours and be interrupted whenever Control quits.
