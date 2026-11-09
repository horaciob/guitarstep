"""Weak spots: a fact you miss comes back today, then after 1, 3 and 7 days right; then it's gone."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from guitarr import progress, quiz, routine
from guitarr.gui.server import app

T = date(2026, 3, 2)


def fact(key, ok, label="x"):
    return dict(key=key, label=label, ok=ok, lesson="intervals", exercise="interval-frets-quiz")


def test_a_missed_fact_comes_back_and_retires_after_three_spaced_rights():
    progress.record_facts([fact("interval_ear:m7", True)], T)                  # never missed: not tracked
    assert progress.weak_facts(today=T) == []
    progress.record_facts([fact("interval_ear:m7", False)], T)
    assert [f["key"] for f in progress.weak_facts(today=T)] == ["interval_ear:m7"]
    day = T
    for gap in progress.FACT_DAYS:
        progress.record_facts([fact("interval_ear:m7", True)], day)
        assert progress.weak_facts(today=day) == []                             # not due again until the gap is over
        day += timedelta(days=gap)
        assert progress.weak_facts(today=day)
    progress.record_facts([fact("interval_ear:m7", True)], day)
    assert "interval_ear:m7" not in progress.get()["facts"]


def test_a_miss_starts_over_and_the_most_missed_come_first():
    for _ in range(3):
        progress.record_facts([fact("read:F#3", False)], T)
    progress.record_facts([fact("read:C4", False)], T)
    progress.record_facts([fact("read:F#3", True)], T)
    progress.record_facts([fact("read:F#3", False)], T + timedelta(days=1))
    weak = progress.weak_facts(today=T + timedelta(days=1))
    assert [f["key"] for f in weak] == ["read:F#3", "read:C4"] and weak[0]["misses"] == 4 and weak[0]["step"] == 0


def test_quiz_answers_feed_the_weak_spots_without_leaking_the_answer():
    c = TestClient(app)
    d = c.post("/api/exercise/draw", json=dict(lesson="naturals-low", exercise="low-names")).json()
    assert all("fact" not in it for it in d["items"])
    full = quiz._draws[d["token"]]["items"]
    wrong = next(ch["id"] for ch in d["items"][0]["choices"] if ch["id"] != full[0]["answer"])
    c.post("/api/exercise/check", json=dict(token=d["token"], index=0, answer=wrong))
    c.post("/api/exercise/check", json=dict(token=d["token"], index=0, answer=full[0]["answer"]))    # only the first counts
    weak = c.get("/api/weak").json()
    assert len(weak) == 1 and weak[0]["key"] == full[0]["fact"]["key"] and weak[0]["route"] == "#/lesson/naturals-low?ex=low-names"
    assert weak[0]["label"]["code"] == "fact_read"
    step = next(s for s in routine.build()["steps"] if s["kind"] == "weak")
    assert step["route"] == weak[0]["route"] and step["params"]["more"] == 0


def test_tool_facts_point_back_to_the_tool():
    assert progress.fact_route(dict(lesson="__tools__", exercise="ear-cycle-7ths")) == "#/tools?tab=ear&ear=cycle&module=7ths"
    assert progress.fact_route(dict(lesson="__tools__", exercise="ear-interval")) == "#/tools?tab=ear&ear=interval"
