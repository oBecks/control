---
status: accepted
---

# A Scene is a state, not steps

Once Automations could have no Triggers and be run by hand (a Run Button, a Hotkey, the Assistant, [ADR 0012](0012-how-an-automation-run-behaves.md)), a "Movie night" could already be a manual-only Automation that sets several Devices. Scenes are still their own thing: a Scene declares how Devices should look, and an Automation says what to do in which order. Being a state is what gives a Scene the two things an Automation can't have: it can tell when it's **active**, and it can be **made from how things are now**.

## Decisions

- **A Scene holds only states.** Devices and Groups, each with only the parts the user ticked (power, brightness, colour, AC mode and temperature, a Streamer's open app). "Lamp off" leaves the lamp's colour alone. Button presses (HDMI 1) and Remote Devices with only a Power Toggle are left out, as in Groups: pressing Power twice switches the Device back off, and neither press has a state to compare. Anything with order, waits, Conditions or buttons is an Automation, which can set a Scene as one of its Actions.
- **Active means every chosen part matches.** Assumed State counts (a Scene of ACs could never light otherwise). A Group matches when all its members do. An Offline Device means the Scene isn't active. Several Scenes can be active at once. Active is worked out from state, never remembered as "the last one set", so a Scene lights up even when someone sets the room by hand.
- **Setting sends everything at once.** A Device that fails doesn't stop the rest: a notice names it. Setting an active Scene sends it again, which fixes an Assumed State a physical remote made wrong. A Scene has no "off": there's no single right state to go back to.
- **Made from now or from empty.** A new Scene starts with nothing in it; each Device added to it is filled in with its current state ("from how things are now"), and every value stays editable afterwards. It's saved once it holds at least one Device: a Scene with nothing in it only exists when forgetting Devices empties one (below).
- **Forgetting a Device or deleting a Group drops only that part.** A Scene left with nothing is kept, marked *needs attention*, and leaves Home, like an Automation losing its last Action.
- **Automations know Scenes three ways:** an Action "Set Scene", a Condition "Scene is active" (cheap, since active is a state), and a Trigger "Scene is set", which fires whoever set it: a person, a Hotkey, the Assistant or another Automation. Saving refuses an Automation that would set off itself through a Scene, and ADR 0012's hop limit counts these Runs too.

## Considered options

- **A Scene is a manual-only Automation shown as a chip**: one model and one builder, but it could never say whether it's active, and capturing the current state doesn't fit a list of steps.
- **No Scenes at all** (pin Automations on Home): the same loss, and "set the room like this" is what people expect a Scene to be.
- **Full state per Device**: simpler, but a Scene saved in summer would reset the lamp's colour picked since.
- **Buttons and Power Toggles in a Scene**: more flexible, but "active" would only ever be partly true, and sending the Scene again would switch toggled Devices back off.
- **Tapping an active Scene undoes it**: feels like a toggle, but the "before" state is stale the moment anything else changes.
- **"Scene is set" fired only by people**: no loops to guard, but "Good night at 23:00 sets Night" would never reach the Automations listening for Night.
