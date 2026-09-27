---
status: accepted
---

# How an Automation's Run behaves

An Automation is When (Triggers, any one starts a Run) → Only if (Conditions, all or any, checked once) → Then (Actions in order: control a Device or Group, run another Automation, wait, notify). Actions that control reuse the Hotkey action model (toggle, set, step, press, open an app, [ADR 0007](0007-hotkeys-registered-with-windows-no-keyboard-hook.md)), so Hotkeys, Automations and the Assistant share one definition and one set of checks. The rules below are the same for every Automation, with no per-Automation settings, so the builder has nothing extra to explain.

## Decisions

- **A new Trigger restarts the Run.** If a Trigger fires while a Run is still waiting, that Run stops and a new one starts. "Light on, wait 10 min, light off" then behaves like a timer that restarts.
- **Never late, but never silent.** If the PC sleeps or Control quits during a Run, the remaining Actions are abandoned, the Run ends as *interrupted*, and a notification names what didn't happen ("Night AC: AC off didn't run"). This extends [ADR 0006](0006-automations-run-in-the-engine.md)'s rule for missed timed Runs to Runs cut in the middle: an AC or plug switching late by surprise is worse than a reminder that it didn't.
- **A failed Action doesn't stop the Run.** The other Actions still happen (one Offline bulb shouldn't keep the AC on), the Run ends as *partly failed*, and a notification says which Action failed.
- **Automations can trigger each other, with a loop guard.** A change an Automation makes fires other Automations' Triggers like any other change. An Automation's own changes never trigger itself; a chain stops after a few hops or too many Runs per minute, and a notification says which Automations were stopped.
- **An Action can run another Automation** (chaining, added 2026-09-27). It starts that one's Run skipping its Only if, like every "Run" (a Hotkey, a Run Button, the Assistant), and whether it's switched on or off, since switching off stops only its Triggers; the Run that started it goes straight on without waiting for it. Saving refuses an Automation that would run itself, directly or through others; the hop limit above also counts these Runs, so a chain that mixes Actions and Device changes still stops. Deleting an Automation removes the Actions that ran it, and one left without Actions is switched off as needing attention.
- **Running by hand skips Only if.** Every Automation has a Run button (and the Assistant's `run_automation`, a Hotkey's "Run Automation", a Dashboard's Run button). The person asked, so Conditions aren't checked. An Automation with no Triggers is valid and runs only by hand.
- **Forgetting a Device or deleting a Group removes only the parts that name it.** Unlike Hotkeys, which are deleted with their target, an Automation loses just those Triggers, Conditions and Actions; if that takes its last Trigger (it would quietly become manual-only) or its last Action, it's switched off and marked *needs attention*. Nothing the user wrote disappears silently.
- **History**: the last 50 Runs of each Automation, each with what triggered it, each Action's result, and how it ended (succeeded, partly failed, skipped by its Conditions, missed, interrupted).

## Considered options

- **Ignore a Trigger while running, run both side by side, or queue it**: each surprises in the common timer case, and letting each Automation choose adds a setting most people can't judge.
- **Run the remaining Actions on wake**: catches up an "off", but equally a late "on".
- **Stop the Run at the first failure**: leaves the rest of the home half done.
- **No chaining**: "when the TV turns on" would then miss the TV turned on by another Automation.
- **A run Action that checks the other Automation's Only if, or waits for its Run to end**: HA-style scripts can, but it needs a per-Action setting; putting the Condition in the first Automation, or a Wait after the run Action, covers most of it.
- **An If / else Action** in Phase 1: more powerful, but the builder gets much harder; two Automations do the same for now.
