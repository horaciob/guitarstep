"""Learning features: chord dictionary, charts (own text format), course exercises passed
by listening, progress (XP, streak, records) and their API."""
import io
import time
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from guitarr import catalog, progress
from guitarr.core import Grid, Note
from guitarr.dsp import Detection, chroma
from guitarr.follow import Judge, TempoFollower, WaitFollower, group_events
from guitarr.gui.server import app
from guitarr.reference import RefOptions, load_reference
from guitarr.session import LiveOptions, LiveSession

SR = 44100
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# ---------------------------------------------------------------- content
def test_chord_dictionary_is_consistent():
    chords = catalog.chords()
    assert len(chords) >= 35
    for c in chords:
        assert len(c["frets"]) == 6 and len(c["fingers"]) == 6
        pcs = {NAMES[(catalog.OPEN_STRINGS[i] + f) % 12] for i, f in enumerate(c["frets"]) if f >= 0}
        assert pcs == set(c["notes"]), c["id"]


def test_builtin_charts_parse_and_use_known_chords():
    rows = catalog.charts()
    assert len(rows) >= 10
    for r in rows:
        assert not r.get("error") and r["missing"] == [], r["id"]


def test_lessons_reference_existing_material():
    for ls in catalog.lessons():
        for c in ls.get("chords", []):
            assert catalog.get_chord(c), (ls["id"], c)
        for ex in ls["exercises"]:
            opts, mode, speed, need = catalog.exercise_setup(ls["id"], ex["id"])
            ref = load_reference(opts, log=lambda m: None)
            assert ref.notes and mode in ("wait", "tempo") and 0 < need <= 100


def test_spanish_translations_cover_all_content():
    import json
    from pathlib import Path

    es = json.loads((Path(catalog.__file__).parent / "gui/static/locales/es.json").read_text())["content"]
    assert set(es["chords"]) == {c["id"] for c in catalog.chords()}
    assert set(es["lessons"]) == {ls["id"] for ls in catalog.lessons()}
    assert set(es["exercises"]) == {f"{ls['id']}/{e['id']}" for ls in catalog.lessons() for e in ls["exercises"]}
    assert set(es["charts"]) == {c["id"] for c in catalog.charts()}


CHART = """title: Test
bpm: 100
time: 3/4
capo: 1
strum: D.DU.U

[A]
Am | % | C G | -   # comment
[B]
E7 | Am
"""


def test_parse_chart_format():
    c = catalog.parse_chart(CHART, "test")
    assert c["title"] == "Test" and c["bpm"] == 100 and c["beats_per_bar"] == 3 and c["capo"] == 1
    assert [(b["chord"], b["beats"]) for b in c["bars"]] == [
        ("Am", 3), ("Am", 3), ("C", 1.5), ("G", 1.5), (None, 3), ("E7", 3), ("Am", 3)]
    assert c["bars"][0]["section"] == "A" and c["bars"][5]["section"] == "B"
    ref = load_reference(RefOptions(chart=c), log=lambda m: None)
    starts = sorted({n.start for n in ref.notes})
    assert len(starts) == 6                        # the "-" bar is silent
    assert ref.grid.bar_of(starts[2]) == (3, 1.0) and ref.grid.bar_of(starts[3]) == (3, 2.5)
    assert ref.capo == 1 and {n.label for n in ref.notes} == {"Am", "C", "G", "E7"}


@pytest.mark.parametrize("text,err", [
    ("title: x\n", "no bars"),
    ("% | G\n", "'%' with no chord"),
    ("time: 13/4\nG\n", "invalid time signature"),
    ("bpm: 5\nG | D\n", "bpm"),
])
def test_parse_chart_errors(text, err):
    with pytest.raises(catalog.CatalogError, match=err):
        catalog.parse_chart(text)


def test_user_charts_save_list_delete():
    with pytest.raises(catalog.CatalogError, match="Unknown chords"):
        catalog.save_chart("title: Weird\nH7 | G\n")
    r = catalog.save_chart("title: My Song!\nG | D\n")
    assert r["id"] == "my-song"
    assert [c["id"] for c in catalog.charts() if c["mine"]] == ["my-song"]
    dup = catalog.save_chart(catalog.chart_text("03-pop-in-g")[0], "03-pop-in-g")
    assert dup["id"] == "03-pop-in-g-mine"        # never overwrites a built-in exercise
    with pytest.raises(catalog.CatalogError):
        catalog.delete_chart("03-pop-in-g")
    catalog.delete_chart("my-song")
    assert "my-song" not in [c["id"] for c in catalog.charts()]


# ---------------------------------------------------------------- judging strummed chords
def synth_strums(chart, wrong_bar=None, wrong_frets=None, lead=0.8, seed=1):
    """Strummed take (Karplus-Strong): one strum per beat, with the capo."""
    from guitarr.demo import pluck

    rng = np.random.default_rng(seed)
    beat = 60 / chart["bpm"]
    total = lead + sum(b["beats"] for b in chart["bars"]) * beat + 1.5
    y = np.zeros(int(SR * total))
    t = lead
    for k, b in enumerate(chart["bars"], start=1):
        frets = wrong_frets if k == wrong_bar else b["frets"]
        for j in range(max(1, int(b["beats"]))):
            for s, f in enumerate(frets):
                if f is None or f < 0:
                    continue
                m = catalog.OPEN_STRINGS[s] + chart["capo"] + f
                x = pluck(440 * 2 ** ((m - 69) / 12), beat * 0.95, rng) * (0.25 if j else 0.35)
                a = int((t + j * beat + s * 0.012) * SR)
                y[a:a + len(x)] += x[:len(y) - a]
        t += b["beats"] * beat
    return (y / np.max(np.abs(y)) * 0.8).astype(np.float32)


def run_chart(tmp_path, chart, **kw):
    import soundfile as sf

    wav = tmp_path / "x.wav"
    sf.write(wav, synth_strums(chart, **kw), SR)
    return LiveSession(load_reference(RefOptions(chart=chart), log=lambda m: None),
                       LiveOptions(mode="tempo", simulate=wav, fast=True, count_extras=False, legato=False)).run()


@pytest.mark.parametrize("cid", [c["id"] for c in catalog.charts()])
def test_every_chart_played_right_has_no_errors(tmp_path, cid):
    r = run_chart(tmp_path, catalog.get_chart(cid))
    assert [i for i in r["issues"] if i["type"] != "timing"] == []


@pytest.mark.parametrize("cid,bar,wrong,grid_bar,label", [
    ("03-pop-in-g", 3, "E", 3, "Em"),             # major instead of minor
    ("05-waltz", 3, "D", 3, "Dm"),                # D instead of Dm, in 3/4
    ("09-anchor-fingers", 2, "C", 2, "G"),        # wrong chord, with capo 2
    ("07-power-chord-rock", 2, "A5", 2, "G5"),    # wrong power chord
])
def test_wrong_chords_are_caught(tmp_path, cid, bar, wrong, grid_bar, label):
    r = run_chart(tmp_path, catalog.get_chart(cid), wrong_bar=bar, wrong_frets=catalog.get_chord(wrong)["frets"])
    bad = [(i["type"], i["bar"], i["label"]) for i in r["issues"] if i["type"] != "timing"]
    assert bad == [("wrong", grid_bar, label)]


def _det(t, pitches):
    tt = np.arange(4096) / SR
    y = sum(np.sin(2 * np.pi * h * 440 * 2 ** ((m - 69) / 12) * tt) / h for m in pitches for h in range(1, 4))
    return Detection(t, None, 0.0, chroma(y, SR), -20.0)


G = [43, 47, 50, 55, 59, 67]
EM = [40, 47, 52, 55, 59, 64]


def _events():
    return group_events([Note(0.0, 1.9, p) for p in G] + [Note(2.0, 3.9, p) for p in EM])


def test_fill_strums_are_not_errors_in_tempo_mode():
    f = TempoFollower(_events(), Judge(), speed=1.0, window=0.2, grid=Grid(np.arange(16) * 0.5, 4),
                      click=False, count_extras=False)
    f.start(0.0)
    f.on_detection(_det(0.0, G))
    for t in (0.5, 1.0, 1.5):
        assert f.on_detection(_det(t, G)) is None
    f.on_detection(_det(2.01, EM))
    f.tick(10)
    assert [e.status for e in f.events] == ["ok", "ok"] and f.extras == []


def test_restrumming_previous_chord_is_not_an_error_in_wait_mode():
    f = WaitFollower(_events(), Judge())
    f.on_detection(_det(0.0, G))
    assert f.on_detection(_det(0.5, G)) is None
    f.on_detection(_det(1.0, EM))
    assert f.events[1].status == "ok" and f.events[1].errors == 0


# ---------------------------------------------------------------- progress
def test_streak_and_levels():
    assert progress.streak(["2026-01-01", "2026-01-02", "2026-01-03"], date(2026, 1, 3)) == 3
    assert progress.streak(["2026-01-01", "2026-01-02"], date(2026, 1, 3)) == 2    # not yet today
    assert progress.streak(["2026-01-01"], date(2026, 1, 3)) == 0
    assert progress.level(0)["level"] == 1 and progress.level(150)["level"] == 2
    assert progress.level(99999)["next_xp"] is None


def _report(score, judged=4, events=4, first=4, fixed=0):
    return dict(summary=dict(score=score, judged=judged, events=events, first_try=first, fixed=fixed),
                reference=dict(name="x"))


def test_exercise_and_lesson_awards():
    lid = "first-change"
    exs = catalog.get_lesson(lid)["exercises"]
    out = progress.on_session(dict(type="exercise", lesson=lid, exercise=exs[0]["id"], min=75), _report(60))
    assert out["passed"] is False and out["xp"] == 0
    out = progress.on_session(dict(type="exercise", lesson=lid, exercise=exs[0]["id"], min=75), _report(90))
    assert out["passed"] and out["xp"] == progress.XP["exercise"]
    again = progress.on_session(dict(type="exercise", lesson=lid, exercise=exs[0]["id"], min=75), _report(95))
    assert again["xp"] == 0                         # passing again doesn't add XP
    for ex in exs[1:]:
        out = progress.on_session(dict(type="exercise", lesson=lid, exercise=ex["id"], min=ex["min"]), _report(100))
    assert out.get("lesson_done") and lid in progress.get()["lessons"]
    p = progress.get()
    assert p["streak"] == 1 and p["practiced_today"]
    assert p["events"][0]["code"] == "lesson_completed" and p["events"][0]["params"] == dict(lesson=lid)
    assert progress.event_text(p["events"][0]) == f"Lesson completed: {lid}"


def test_chord_and_drill_awards():
    out = progress.on_session(dict(type="chord", chord="Em"), _report(100, judged=1, events=1, first=1))
    assert out["passed"] and out["xp"] == progress.XP["chord"]
    assert progress.chord_mastered("Em", "camera")["xp"] == 0          # already mastered
    d = progress.on_session(dict(type="drill", chords=["Em", "Am"]), _report(None, judged=21, events=60, first=20, fixed=1))
    assert d["changes"] == 20 and d["record"] and d["xp"] == 10
    d = progress.on_session(dict(type="drill", chords=["Em", "Am"]), _report(None, judged=5, events=60, first=5))
    assert d["record"] is False and d["best"] == 20


def test_simulated_practice_gives_no_xp():
    r = _report(100)
    r["simulated"] = True
    assert progress.on_session(dict(type="practice"), r)["xp"] == 0


# ---------------------------------------------------------------- API
def test_api_learning_endpoints():
    c = TestClient(app)
    assert {g["id"] for g in c.get("/api/chords").json()["groups"]} >= {"barre", "power"}
    assert len(c.get("/api/charts").json()) >= 10
    assert c.get("/api/charts/03-pop-in-g").json()["chart"]["bpm"] == 90
    v = c.post("/api/charts/validate", json=dict(text="G | X9")).json()
    assert v["ok"] is False and v["unknown"] == ["X9"]
    saved = c.post("/api/charts", json=dict(text="title: Mine\nG | C\n")).json()
    assert c.post("/api/preview", json=dict(chart=saved["id"])).status_code == 200
    assert c.delete(f"/api/charts/{saved['id']}").json()["ok"]
    course = c.get("/api/course").json()
    assert course["next"]["id"] == "strings"
    bad = c.post("/api/progress/tutorial", json=dict(lesson="strings", url="javascript:alert(1)"))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "bad_url"
    c.post("/api/progress/tutorial", json=dict(lesson="strings", url="https://www.youtube.com/watch?v=abcdefghijk"))
    assert c.get("/api/course").json()["levels"][0]["lessons"][0]["pinned"].endswith("abcdefghijk")
    assert c.post("/api/progress/chord", json=dict(chord="Em", via="camera")).json()["xp"] == progress.XP["chord"]
    assert c.post("/api/progress/chord", json=dict(chord="Zz", via="camera")).status_code == 400
    for path in ("/static/main.js", "/static/views/camera.js", "/static/vendor/tasks-vision/vision_bundle.mjs",
                 "/static/vendor/i18next/i18next.js", "/static/locales/en.json", "/static/locales/es.json"):
        assert c.get(path).status_code == 200, path
    assert c.get("/static/vendor/mediapipe/wasm/vision_wasm_internal.wasm").headers["content-type"] == "application/wasm"


def _upload(c, wav_bytes, name):
    c.post("/api/takes", files=dict(file=(name, wav_bytes)))


def _wait_report(c):
    for _ in range(200):
        st = c.get("/api/live/state").json()
        if st.get("report"):
            return st["report"]
        time.sleep(0.05)
    return c.post("/api/live/stop").json()["report"]


def _wav(chart):
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, synth_strums(chart, lead=0.5), SR, format="WAV")
    return buf.getvalue()


@pytest.mark.parametrize("played,ok", [("Em", True), ("E", False)])
def test_chord_check_by_ear_over_api(played, ok):
    c = TestClient(app)
    _upload(c, _wav(dict(bpm=60, capo=0, bars=[dict(beats=4, frets=catalog.get_chord(played)["frets"])])), "r.wav")
    assert c.post("/api/live/start", json=dict(chord="Em", simulate="r.wav", fast=True)).status_code == 200
    rep = _wait_report(c)
    assert rep["award"]["passed"] is ok
    assert ("Em" in c.get("/api/progress").json()["chords"]) is ok


def test_lesson_exercise_over_api():
    c = TestClient(app)
    chart = catalog.chart_from_chord("Em", 4)
    _upload(c, _wav(dict(chart, bpm=60)), "em4.wav")
    r = c.post("/api/live/start", json=dict(exercise=dict(lesson="e-minor", exercise="em-x4"), simulate="em4.wav", fast=True))
    assert r.status_code == 200 and r.json()["context"]["type"] == "exercise"
    rep = _wait_report(c)
    assert rep["award"]["passed"] and rep["award"]["lesson_done"]
    assert c.get("/api/course").json()["levels"][0]["lessons"][1]["done"]


def test_chord_change_minute_over_api():
    c = TestClient(app)
    chart = catalog.chart_alternating(["Em", "Am"], 5)            # 10 clean strums = 9 changes
    _upload(c, _wav(dict(chart, bpm=90)), "changes.wav")
    r = c.post("/api/live/start", json=dict(drill=dict(chords=["Em", "Am"], seconds=60), simulate="changes.wav", fast=True))
    assert r.status_code == 200
    a = _wait_report(c)["award"]
    assert a["changes"] == 9 and a["record"] and a["xp"] == 4
    assert c.get("/api/progress").json()["drills"]["Em-Am"] == 9


def test_live_messages_are_structured():
    c = TestClient(app)
    _upload(c, _wav(dict(bpm=60, capo=0, bars=[dict(beats=4, frets=catalog.get_chord("E")["frets"])])), "e.wav")
    c.post("/api/live/start", json=dict(chord="Em", simulate="e.wav", fast=True))
    rep = _wait_report(c)
    st = c.get("/api/live/state").json()["state"]
    last = st["last"]
    assert last["code"] == "wrong" and last["params"]["detail"]["kind"] == "chord_wrong"
    assert last["text"].startswith("✗ chord: missing G (minor 3rd)")
    assert rep["issues"][0]["detail"]["kind"] == "chord_wrong"
