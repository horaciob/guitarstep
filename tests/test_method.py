"""The teaching method (roadmap D): steps, guidance levels, variations, testing out, recaps, sections, hints."""
from fastapi.testclient import TestClient

from guitarr import catalog, progress, quiz
from guitarr.gui.server import app


def lesson_of(c, lid):
    return next(ls for lv in c.get("/api/course").json()["levels"] for ls in lv["lessons"] if ls["id"] == lid)


def test_lesson_flow_steps_and_separate_meters():
    c = TestClient(app)
    ls = lesson_of(c, "intervals")
    assert [s["step"] for s in ls["flow"]] == list(catalog.STAGES)
    assert not ls["flow"][0]["done"]
    assert ls["understood"] == dict(done=0, total=1) and ls["played"] == dict(done=0, total=2)
    c.post("/api/lesson/seen", json=dict(lesson="intervals"))
    ls = lesson_of(c, "intervals")
    assert ls["flow"][0]["done"]                                   # discovered
    stages = {e["id"]: e["stage"] for e in ls["exercises"]}
    assert stages == {"interval-frets-quiz": "understand", "play-3-5-8": "guided", "play-m3-4-6": "guided"}


def test_guidance_levels_and_variations_are_recorded_apart():
    with progress._lock:
        d = progress._read()
        a = progress._record_exercise(d, "major-scale", "g-position", 90, 80, guidance=2, hints=1)
        v = progress._record_exercise(d, "major-scale", "g-position", 85, 80, variant=True)
        progress._write(d)
    assert a["passed"] and a["guidance"] == 2 and a["hints"] == 1
    assert v["variant"] and v["xp"] == progress.XP["variation"]
    p = progress.get()
    assert p["guidance"]["major-scale/g-position"] == 2 and p["variations"]["major-scale/g-position"] == 85
    assert p["exercises"]["major-scale/g-position"] == 90             # the variation doesn't overwrite it


def test_variation_endpoint_moves_the_exercise():
    c = TestClient(app)
    r = c.post("/api/exercise/variation", json=dict(lesson="major-scale", exercise="g-position")).json()
    assert r["label"] == dict(code="in_key", key="C") and r["steps"][0]["pitch"] % 12 == 0
    assert c.post("/api/exercise/variation", json=dict(lesson="intervals", exercise="interval-frets-quiz")).json()["detail"]["code"] == "no_variation"
    ex = catalog.get_exercise("major-scale", "g-position")
    opts, *_ = catalog.exercise_setup("major-scale", "g-position", variant=True)
    assert opts.tab[0]["pitch"] % 12 == 0 and catalog.exercise_steps(ex)[0]["pitch"] % 12 == 7


def test_test_out_needs_the_questions_first_then_completes_the_lesson():
    c = TestClient(app)
    # the playing part is locked until the questions are passed
    r = c.post("/api/live/start", json=dict(exercise=dict(lesson="intervals", exercise="play-m3-4-6", testout=True)))
    assert r.json()["detail"]["code"] == "testout_quiz"
    d = c.post("/api/lesson/testout", json=dict(lesson="intervals")).json()
    assert d["final"] == "play-m3-4-6" and len(d["items"]) == 2 and d["play_need"] == 90
    for i, it in enumerate(quiz._draws[d["token"]]["items"]):
        c.post("/api/exercise/check", json=dict(token=d["token"], index=i, answer=it["answer"]))
    fin = c.post("/api/lesson/testout/finish", json=dict(token=d["token"])).json()
    assert fin["award"]["passed"] and fin["final"] == "play-m3-4-6" and quiz.testout_ready("intervals")
    # a lesson with nothing to play is done as soon as its questions pass
    d = c.post("/api/lesson/testout", json=dict(lesson="interval-ear")).json()
    assert d["final"] == "ear-echo"
    with progress._lock:
        dd = progress._read()
        out = progress._test_out(dd, "interval-ear")
        progress._write(dd)
    assert out["lesson_done"] and "interval-ear" in progress.get()["tested_out"]
    assert all(e["passed"] for e in lesson_of(c, "interval-ear")["exercises"])


def test_level_recaps_are_generated_from_the_level():
    recaps = [ls for ls in catalog.lessons() if ls.get("recap")]
    assert recaps and all(2 <= len(ls["exercises"]) <= catalog.RECAP_MAX for ls in recaps)
    r = next(ls for ls in recaps if ls["id"] == "recap-n8")
    for e in r["exercises"]:
        src = catalog.get_exercise(*e["from"].split("/"))
        assert {k: v for k, v in e.items() if k not in ("id", "from")} == {k: v for k, v in src.items() if k != "id"}
    assert catalog.get_exercise("recap-n8", r["exercises"][0]["id"])


def test_sections_states_tempo_and_mastery():
    c = TestClient(app)
    s = c.get("/api/charts/25-song-form-aaba/sections").json()
    assert [x["key"] for x in s["sections"]] == ["A", "A (2)", "B", "A (3)"] and s["mastery"] == 0
    assert s["sections"][2]["from"] == 17 and s["sections"][2]["to"] == 24
    s = c.post("/api/charts/25-song-form-aaba/sections", json=dict(key="B", state="ready", bpm=120)).json()
    assert s["sections"][2]["state"] == "ready" and s["sections"][2]["bpm"] == 120 and s["mastery"] == 25
    assert c.post("/api/charts/25-song-form-aaba/sections", json=dict(key="B", bpm=5)).json()["detail"]["code"] == "bad_bpm"
    assert c.post("/api/charts/25-song-form-aaba/sections", json=dict(key="Z", state="ready")).json()["detail"]["code"] == "bad_section"


def test_glossary_and_hint_endpoints():
    c = TestClient(app)
    g = c.get("/api/glossary").json()["terms"]
    assert "guide_tones" in g and g["half_step"]["term"] == "half step"
    assert c.post("/api/live/hint").status_code == 404                # nothing is listening


def test_reviews_link_straight_to_the_exercise():
    from guitarr import routine
    with progress._lock:
        d = progress._read()
        d["reviews"]["exercise:major-scale/g-position"] = dict(step=0, due="2000-01-01", last=None)
        progress._write(d)
    steps = routine.build()["steps"]
    rev = next(s for s in steps if s["kind"] == "review_exercise")
    assert rev["route"] == "#/lesson/major-scale?ex=g-position"
