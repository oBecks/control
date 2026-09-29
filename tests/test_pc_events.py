from control.desktop import events


def test_windows_messages_become_pc_events():
    assert events.event_of(events.WM_POWERBROADCAST, events.PBT_APMSUSPEND, 0) == "sleeps"
    assert events.event_of(events.WM_POWERBROADCAST, events.PBT_APMRESUMEAUTOMATIC, 0) == "wakes"
    assert events.event_of(events.WM_POWERBROADCAST, 0x7, 0) is None  # a battery notice, say
    assert events.event_of(events.WM_WTSSESSION_CHANGE, events.WTS_SESSION_LOCK, 1) == "locks"
    assert events.event_of(events.WM_WTSSESSION_CHANGE, events.WTS_SESSION_UNLOCK, 1) == "unlocks"
    assert events.event_of(events.WM_WTSSESSION_CHANGE, events.WTS_SESSION_LOGON, 1) == "unlocks"
    assert events.event_of(events.WM_WTSSESSION_CHANGE, 0x6, 1) is None  # logoff: the shutdown message covers it
    assert events.event_of(events.WM_ENDSESSION, 1, 0) == "shuts_down"
    assert events.event_of(events.WM_ENDSESSION, 0, 0) is None  # another app said no
    assert events.event_of(0x0001, 1, 0) is None


def test_the_same_event_twice_in_a_moment_is_told_once(monkeypatch):
    told = []
    e = events.PcEvents(8321)
    monkeypatch.setattr(e, "_post", lambda event, wait: told.append((event, wait)))
    clock = iter([100.0, 101.0, 140.0])
    monkeypatch.setattr(events.time, "monotonic", lambda: next(clock))

    class Now:  # run the thread's work at once
        def __init__(self, target, args, **_):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(events.threading, "Thread", Now)
    e.tell("wakes")
    e.tell("wakes")  # a second later: the lock screen waking again
    e.tell("wakes")  # 40 s later: really another wake
    assert told == [("wakes", 0), ("wakes", 0)]


def test_going_to_sleep_and_shutting_down_wait_for_the_runs(monkeypatch):
    told = []
    e = events.PcEvents(8321)
    monkeypatch.setattr(e, "_post", lambda event, wait: told.append((event, wait)))
    e.tell("sleeps")
    e.tell("shuts_down")
    assert told == [("sleeps", 2.5), ("shuts_down", 2.5)]
