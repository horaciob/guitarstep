"""Practice tools (roadmap E): rhythm test, ear training, melodic echo, strums, stats and the time budget."""
from fastapi.testclient import TestClient

from guitarr import catalog, progress, quiz, routine
from guitarr.gui.server import app, ref_options
from guitarr.reference import load_reference


def test_rhythm_stats_bins_have_counts():
    s = progress.rhythm_stats([-40, -5, 0, 12, 35, 120])
    assert s["n"] == 6 and s["within"] == 50 and sum(b["count"] for b in s["bins"]) == 6
    assert next(b for b in s["bins"] if b["lo"] == -10)["count"] == 2
    assert progress.rhythm_stats([])["n"] == 0


def test_rhythm_echo_and_strum_sources_build_references():
    opts, ctx = ref_options(dict(rhythm=dict(bpm=90, bars=2, chord="Am")))
    ref = load_reference(opts, log=lambda m: None)
    assert ctx == dict(type="rhythm", mode="tempo", bpm=90.0, bars=2) and len({n.start for n in ref.notes}) == 8
    quiz.draw("__tools__", quiz.TOOLS_ECHO, 75, seed=1)
    opts, ctx = ref_options(dict(echo=True))
    ref = load_reference(opts, log=lambda m: None)
    assert ctx["type"] == "echo" and [n.pitch for n in ref.notes] == quiz.drawn_notes("__tools__", quiz.TOOLS_ECHO)
    opts, ctx = ref_options(dict(strum=dict(pattern="folk", chords=["G", "C"])))
    assert opts.chart["strum"] == "D.DU.UDU" and len(opts.chart["bars"]) == 4


def test_echo_in_a_lesson_is_played_on_the_metronome():
    opts, mode, speed, need = catalog.exercise_setup("interval-ear", "ear-echo")
    assert mode == "tempo" and opts.timed and opts.bpm == 72
    starts = [n["start"] for n in opts.timed]
    assert starts == sorted(starts) and opts.timed[-1]["pitch"] % 12 == 9          # ends on A, the root


def test_session_results_for_rhythm_and_echo():
    rep = dict(summary=dict(score=90, judged=8, events=8, timing_ms=[-12, 4, 20, 31, -3, 8, 0, 15]))
    out = progress.on_session(dict(type="rhythm", bpm=80), rep)
    assert out["rhythm"]["n"] == 8 and out["xp"] == 5 and progress.get()["rhythm"]["80"]["std"] == out["rhythm"]["std"]
    out = progress.on_session(dict(type="echo"), dict(summary=dict(score=80)))
    assert out["passed"] and progress.get()["ear"]["echo"]["best"] == 80


def test_ear_training_rounds_and_chord_shapes():
    c = TestClient(app)
    d = c.post("/api/ear/draw", json=dict(kind="chord_quality", count=4)).json()
    assert len(d["items"]) == 4 and len(d["items"][0]["choices"]) == 6
    for i, it in enumerate(quiz._draws[d["token"]]["items"]):
        r = c.post("/api/exercise/check", json=dict(token=d["token"], index=i, answer=it["answer"])).json()
        assert r["correct"] and len(r["reveal"]["frets"]) == 6               # the shape of what you heard
    r = c.post("/api/ear/finish", json=dict(token=d["token"])).json()
    assert r["summary"]["score"] == 100 and r["award"]["best"] == 100 and r["award"]["xp"] == 5
    assert c.post("/api/ear/draw", json=dict(kind="nope")).json()["detail"]["code"] == "bad_kind"


def test_strum_library_and_stats():
    c = TestClient(app)
    pats = c.get("/api/strums").json()["patterns"]
    assert {p["time"] for p in pats} == {"4/4", "3/4", "6/8"}
    for p in pats:                                  # one slot per eighth note of the bar
        bpb = int(p["time"].split("/")[0])
        assert len(p["strum"]) == (bpb if p["time"] == "6/8" else bpb * 2)
    s = c.get("/api/stats").json()
    assert len(s["days"]) == 365 and s["totals"]["active_days"] == 0 and s["tempo"] == []


def test_time_budget_fits_the_plan():
    c = TestClient(app)
    for b in progress.BUDGETS:
        r = c.post("/api/today/budget", json=dict(minutes=b)).json()
        assert r["budget"] == b and r["minutes"] == b
        assert r["steps"][0]["kind"] == "tune"
    assert c.post("/api/today/budget", json=dict(minutes=45)).json()["detail"]["code"] == "bad_budget"
    r = c.post("/api/today/budget", json=dict(minutes=None)).json()
    assert r["budget"] is None
    steps = [dict(kind="tune", minutes=2), dict(kind="lesson", minutes=10), dict(kind="chart", minutes=8), dict(kind="drill", minutes=2)]
    assert [s["minutes"] for s in routine.fit_budget(steps, 15)] == [2, 10, 3]           # the chart shrinks, the drill waits
