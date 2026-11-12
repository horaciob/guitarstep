"""This week's challenges."""
from datetime import date

from guitarr import progress, weekly

WED = date(2026, 11, 11)


def test_three_picks_that_change_with_the_week():
    a, b = weekly.picks("2026-W46"), weekly.picks("2026-W47")
    assert len(set(a)) == 3 and a[0] == "days5" and a != b
    assert all(c in weekly.CHALLENGES for c in a + b)
    assert weekly.week_days(WED)[0] == "2026-11-09" and weekly.week_id(WED) == "2026-W46"


def test_counting_and_the_bonus_once(monkeypatch):
    monkeypatch.setattr(weekly, "picks", lambda wid: ["days5", "drill3", "neck3"])
    d = progress._empty()
    d["days"] = ["2026-11-09", "2026-11-10"]
    assert weekly.on_award(d, "drill", WED) == [] and weekly.on_award(d, "drill", WED) == []
    assert weekly.on_award(d, "drill", WED) == ["drill3"]
    assert weekly.on_award(d, "drill", WED) == []                          # done once
    v = {c["id"]: c for c in weekly.view(d, WED)["challenges"]}
    assert v["drill3"] == dict(id="drill3", n=3, need=3, done=True) and v["days5"]["n"] == 2
    weekly.on_award(d, "neck", date(2026, 11, 16))                           # next week: the old one is dropped
    assert list(d["weekly"]) == ["2026-W47"]


def test_a_completed_challenge_pays_its_bonus(monkeypatch):
    monkeypatch.setattr(weekly, "picks", lambda wid: ["days5", "rhythm2", "ear3"])
    for _ in range(2):
        progress.on_session(dict(type="rhythm", bpm=80), dict(summary=dict(timing_ms=[5, -3, 8, 0, 2, -6, 4, 1])))
    p = progress.get()
    assert [e["code"] for e in p["events"][:2]] == ["challenge", "rhythm"]
    assert p["xp"] == 5 + 5 + weekly.BONUS_XP
