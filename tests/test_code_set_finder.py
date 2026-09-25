from control.engine import code_set_finder

from .test_climate import SIGNALS, FakeTransmitter


def ranged(lo: int, hi: int) -> dict:
    temps = {str(t): "x" for t in range(lo, hi + 1)}
    return {**SIGNALS, "minTemperature": lo, "maxTemperature": hi, "commands": {"off": "x", "cool": {"auto": temps}}}


def test_plan_gives_distinct_temps_within_each_range():
    sets = {1: ranged(16, 30), 2: ranged(16, 30), 3: ranged(22, 23), 4: ranged(17, 30)}
    assigned, skipped = code_set_finder.plan(sets)
    assert skipped == []
    assert len(set(assigned.values())) == 4
    for code, t in assigned.items():
        assert str(t) in sets[code]["commands"]["cool"]["auto"]
    # The narrow set got a temperature before the wide ones used it up.
    assert assigned[3] in (22, 23)


def test_plan_skips_when_temps_run_out():
    sets = {i: ranged(22, 23) for i in range(3)}
    assigned, skipped = code_set_finder.plan(sets)
    assert len(assigned) == 2 and len(skipped) == 1


def test_run_sends_one_signal_per_set():
    tx = FakeTransmitter()
    sets = {1: SIGNALS, 2: SIGNALS}
    code_set_finder.run(tx, sets, {1: 24, 2: 25}, gap=0)
    assert tx.sent == [b"C-A-24", b"C-A-25"]


def test_plan_only_uses_temps_that_have_signals():
    # SIGNALS declares 16-30 but only has cool/auto signals for 24 and 25.
    assigned, skipped = code_set_finder.plan({1: SIGNALS, 2: SIGNALS, 3: SIGNALS})
    assert sorted(assigned.values()) == [24, 25] and len(skipped) == 1
