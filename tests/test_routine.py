"""Today's practice and spaced review."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from guitarr import progress, routine
from guitarr.gui.server import app

TODAY = date.today()


def kinds(r):
    return [s["kind"] for s in r["steps"]]


def test_a_new_user_gets_a_full_routine():
    r = routine.build()
    assert kinds(r) == ["tune", "lesson", "chart", "drill"]
    lesson = r["steps"][1]
    assert lesson["params"]["lesson"] == "six-strings" or lesson["route"].startswith("#/lesson/")
    assert r["steps"][2]["route"].startswith("#/practice?chart=")
    assert r["minutes"] == sum(s["minutes"] for s in r["steps"]) and r["done"] == 0
    assert r["goal"] == 30


def test_review_schedule_moves_forward_and_resets():
    d = progress._empty()
    progress._review(d, "chord:Em", True, TODAY)
    r = d["reviews"]["chord:Em"]
    assert r["step"] == 0 and r["due"] == (TODAY + timedelta(days=1)).isoformat()
    progress._review(d, "chord:Em", True, TODAY)                     # early: no skipping ahead
    assert r["step"] == 0
    progress._review(d, "chord:Em", True, TODAY + timedelta(days=1))
    assert r["step"] == 1 and r["due"] == (TODAY + timedelta(days=4)).isoformat()
    progress._review(d, "chord:Em", False, TODAY + timedelta(days=4))
    assert r["step"] == 0 and r["due"] == (TODAY + timedelta(days=5)).isoformat()
    progress._review(d, "chord:Am", False, TODAY)                    # failing something new schedules nothing
    assert "chord:Am" not in d["reviews"]


def test_passing_the_last_review_retires_it():
    d = progress._empty()
    last = len(progress.REVIEW_DAYS) - 1
    d["reviews"]["exercise:blues-bends/bend-g7"] = dict(step=last, due=TODAY.isoformat(), last=None)
    progress._review(d, "exercise:blues-bends/bend-g7", True, TODAY)
    assert d["reviews"]["exercise:blues-bends/bend-g7"]["retired"]
    assert progress.due_reviews(d, TODAY + timedelta(days=400)) == []
    progress._review(d, "exercise:blues-bends/bend-g7", True, TODAY + timedelta(days=400))   # still retired
    assert d["reviews"]["exercise:blues-bends/bend-g7"]["retired"]
    progress._review(d, "exercise:blues-bends/bend-g7", False, TODAY + timedelta(days=401))  # lost it: starts over
    r = d["reviews"]["exercise:blues-bends/bend-g7"]
    assert "retired" not in r and r["step"] == 0 and progress.due_reviews(d, TODAY + timedelta(days=402))


def test_due_reviews_show_up_and_tick_when_done():
    d = progress._read()
    d["reviews"]["chord:G"] = dict(step=1, due=(TODAY - timedelta(days=1)).isoformat(), last=None)
    progress._write(d)
    r = routine.build()
    step = next(s for s in r["steps"] if s["id"] == "chord:G")
    assert step["kind"] == "review_chord" and not step["done"] and step["route"] == "#/chords?chord=G"
    progress.on_session(dict(type="chord", chord="G"), dict(summary=dict(judged=1, first_try=1)))
    step = next(s for s in routine.build()["steps"] if s["id"] == "chord:G")
    assert step["done"]
    assert progress._read()["reviews"]["chord:G"]["step"] == 2


def test_chords_mastered_before_reviews_existed_get_scheduled():
    d = progress._read()
    d["chords"]["C"] = dict(ear=(TODAY - timedelta(days=10)).isoformat())
    progress._write(d)
    assert "chord:C" in [s["id"] for s in routine.build()["steps"]]


def test_tune_check_and_drill_detection():
    c = TestClient(app)
    r = c.post("/api/today/check", json=dict(step="tune")).json()
    assert r["steps"][0]["done"] and r["done"] == 1
    assert c.post("/api/today/check", json=dict(step="tune", done=False)).json()["steps"][0]["done"] is False
    assert c.post("/api/today/check", json=dict(step="lesson:x")).json()["detail"]["code"] == "bad_step"
    drill = next(s for s in routine.build()["steps"] if s["kind"] == "drill")
    progress.on_session(dict(type="drill", chords=drill["params"]["chords"]), dict(summary=dict(first_try=5, fixed=0)))
    assert next(s for s in routine.build()["steps"] if s["kind"] == "drill")["done"]
    assert c.get("/api/today").json()["date"] == TODAY.isoformat()
