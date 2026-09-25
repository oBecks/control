"""Code Set Finder: which of a brand's Code Sets does this AC understand?

Send "on" from every candidate Code Set, each with a different target temperature.
Whatever temperature the AC ends up showing names the Code Set that worked.
One question for the user ("what number does it show?") instead of trial and error.
"""

import time

from .climate import ClimateState, RemoteClimate, Transmitter, features_from_signals

PREFERRED_TEMPS = [22, 23, 24, 25, 21, 26, 20, 27, 19, 28, 18, 29, 17, 30, 16, 31, 32]


def available_temps(signals: dict) -> set[int]:
    """Whole-degree temperatures this Code Set really has a probe Signal for
    (the declared min/max range isn't always fully populated)."""
    state = probe_state(signals, 0)
    node = signals["commands"].get(state.mode, {})
    for level in (state.fan, state.swing):
        if isinstance(node, dict) and level in node:
            node = node[level]
    if not isinstance(node, dict):
        return set()
    return {int(float(k)) for k in node if float(k).is_integer()}


def plan(sets: dict[int, dict]) -> tuple[dict[int, int], list[int]]:
    """Give each Code Set a distinct whole-degree temperature it has a Signal for.
    Returns (code -> temp, codes that couldn't get one and need another round)."""
    temps = {code: available_temps(signals) for code, signals in sets.items()}
    assigned: dict[int, int] = {}
    skipped: list[int] = []
    used: set[int] = set()
    # Fewest options first, so they aren't starved by sets with many.
    for code in sorted(sets, key=lambda c: len(temps[c])):
        temp = next((t for t in PREFERRED_TEMPS if t in temps[code] and t not in used), None)
        if temp is None:
            skipped.append(code)
        else:
            assigned[code] = temp
            used.add(temp)
    return assigned, skipped


def probe_state(signals: dict, temp: int) -> ClimateState:
    f = features_from_signals(signals)
    return ClimateState(
        on=True,
        mode="cool" if "cool" in f.modes else f.modes[0],
        target_temp=float(temp),
        fan="auto" if "auto" in f.fan_modes else (f.fan_modes[-1] if f.fan_modes else ""),
        swing=f.swing_modes[0] if f.swing_modes else None,
    )


def run(transmitter: Transmitter, sets: dict[int, dict], assignment: dict[int, int], gap: float = 1.5) -> None:
    """Send the probe, in assignment order, pausing so the AC processes each one."""
    for i, (code, temp) in enumerate(assignment.items()):
        if i:
            time.sleep(gap)
        state = probe_state(sets[code], temp)
        RemoteClimate(sets[code], transmitter, None).apply(
            on=True, mode=state.mode, target_temp=state.target_temp, fan=state.fan, swing=state.swing
        )
