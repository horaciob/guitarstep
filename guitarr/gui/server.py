"""Web UI: local server (FastAPI) + a web page in your browser.

Audio is still processed in Python (sounddevice, low latency); the browser only shows
the state it receives over a WebSocket ~20 times per second.

API errors are `{"detail": {"code": ..., "message": ...}}`: the UI translates `code`
and falls back to the English `message`.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import __version__, backup, catalog, config, history, plan, progress, reminder, rig, routine, signalcheck
from ..audio_io import AudioError, FileSource, MicSource, devices
from ..reference import REFERENCE_EXT, RefOptions, ReferenceError, list_tracks, load_reference

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="guitarr", docs_url=None, redoc_url=None)


def fail(status: int, code: str, message: str):
    raise HTTPException(status, detail=dict(code=code, message=message))


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Make the browser revalidate JS/CSS (via ETag) so it never runs stale versions."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.session = None          # LiveSession
        self.thread: threading.Thread | None = None
        self.section: dict | None = None
        self.ctx: dict | None = None     # what the session is for: practice, exercise, chord, drill
        self.final: dict | None = None   # report + what was earned (once progress was recorded)
        self.tuner = None
        self.probe = None            # signal check: live input
        self.signal: dict = {}       # signal check: results and clips per step
        self.calib: dict = dict(running=False)


S = State()


# ---------------------------------------------------------------- helpers
def _safe_name(name: str) -> str:
    n = Path(name or "").name
    if not n or n.startswith("."):
        fail(400, "bad_filename", "Invalid file name")
    return n


def song_path(name: str) -> Path:
    p = config.SONGS_DIR / _safe_name(name)
    if not p.exists():
        fail(404, "song_not_found", f"Song '{name}' not found")
    return p


def take_path(name: str) -> Path:
    p = config.TAKES_DIR / _safe_name(name)
    if not p.exists():
        fail(404, "take_not_found", f"Take '{name}' not found")
    return p


def audio_settings() -> dict:
    a = dict(config.load()["audio"])
    if a.get("device") is None:
        try:
            a["device"] = devices()["suggested"]
        except AudioError:
            pass
    a.setdefault("channel", 1)
    return a


def ref_options(body: dict) -> tuple[RefOptions, dict]:
    """Builds the requested reference and its context. Sources: an uploaded file (song),
    a chart, a single chord, a course exercise or the chord-change minute (drill)."""
    common = dict(start_bar=_int(body.get("start_bar")), end_bar=_int(body.get("end_bar")))
    try:
        if body.get("exercise"):
            from .. import quiz

            req = body["exercise"]
            lid, eid = req["lesson"], req["exercise"]
            variant, testout = bool(req.get("variant")), bool(req.get("testout"))
            if testout and not quiz.testout_ready(lid):
                fail(400, "testout_quiz", "Answer the questions of the check first")
            opts, mode, speed, need = catalog.exercise_setup(lid, eid, variant=variant)
            ctx = dict(type="exercise", lesson=lid, exercise=eid, min=need, mode=mode, speed=speed,
                       guidance=max(0, min(2, _int(req.get("guidance")) or 0)), hints=0, variant=variant, testout=testout)
            if testout:
                ctx["min"] = max(need, quiz.TESTOUT_PLAY_NEED)
            if mode == "bend":
                ctx["hold"] = float(catalog.get_exercise(lid, eid).get("hold", 1.0))
            return opts, ctx
        if body.get("rhythm"):                        # strum on every beat; the listener measures each strum's timing
            r = body["rhythm"]
            bpm = max(40.0, min(200.0, _float(r.get("bpm")) or 80.0))
            bars = max(2, min(16, _int(r.get("bars")) or 4))
            chord = r.get("chord") or "Em"
            if catalog.get_chord(chord) is None:
                fail(400, "bad_chord", "Unknown chord")
            frets = catalog.get_chord(chord)["frets"]
            chart = dict(id="rhythm", title="rhythm", bpm=bpm, beats_per_bar=4, capo=0,
                         bars=[dict(chord=chord, beats=1, frets=frets) for _ in range(bars * 4)])
            return RefOptions(chart=chart), dict(type="rhythm", mode="tempo", bpm=bpm, bars=bars)
        if body.get("warmup"):                        # a daily warm-up drill, played on the metronome
            from .. import warmup
            w = body["warmup"]
            drill = w.get("drill")
            if drill not in warmup.DRILLS:
                fail(400, "bad_drill", "Unknown drill")
            bpm = max(30.0, min(240.0, _float(w.get("bpm")) or warmup.goal(progress.get()["warmup"], drill)))
            key, pos = w.get("key") or "A", int(w.get("position") or 0)
            return RefOptions(timed=warmup.timed(drill, key, pos), bpm=bpm), dict(type="warmup", mode="tempo", drill=drill, bpm=bpm)
        if body.get("echo"):                          # the phrase drawn in the tools (melodic echo)
            from .. import quiz
            ex = quiz.TOOLS_ECHO
            return RefOptions(timed=quiz.drawn_timed("__tools__", ex), bpm=float(ex["bpm"])), dict(type="echo", mode="tempo")
        if body.get("strum"):                         # a strumming pattern over two chords, graded on the changes
            pat = next((p for p in _strums() if p["id"] == body["strum"].get("pattern")), None)
            chords = [c for c in (body["strum"].get("chords") or ["G", "C"]) if catalog.get_chord(c)][:4]
            if not pat or len(chords) < 2:
                fail(400, "bad_strum", "Pick a pattern and two chords")
            bpb = int(pat["time"].split("/")[0])
            chart = dict(id=f"strum-{pat['id']}", title=pat["name"], bpm=_float(body["strum"].get("bpm")) or 80, beats_per_bar=bpb,
                         capo=0, strum=pat["strum"], bars=[dict(chord=c, beats=bpb, frets=catalog.get_chord(c)["frets"])
                                                            for _ in range(2) for c in chords])
            return RefOptions(chart=chart), dict(type="practice", chart=True)
        if body.get("drill"):
            chords = list(body["drill"]["chords"])[:2]
            return RefOptions(chart=catalog.chart_alternating(chords, 60)), dict(
                type="drill", chords=chords, mode="wait", seconds=int(body["drill"].get("seconds", 60)))
        if body.get("chord"):
            return RefOptions(chart=catalog.chart_from_chord(body["chord"])), dict(
                type="chord", chord=body["chord"], mode="wait")
        if body.get("chart"):
            return RefOptions(chart=catalog.get_chart(body["chart"]), **common), dict(type="practice", chart=True)
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))
    if not body.get("song"):
        fail(400, "no_song", "Pick a song")
    return RefOptions(
        path=song_path(body["song"]), track=body.get("track") or None,
        bpm=_float(body.get("bpm")), first_beat=_float(body.get("first_beat")) or 0.0,
        beats_per_bar=_int(body.get("beats_per_bar")) or 4, separate=bool(body.get("separate")), **common,
    ), dict(type="practice")


def ref_from(body: dict):
    opts, _ = ref_options(body)
    try:
        return load_reference(opts, log=lambda m: None)
    except ReferenceError as e:
        fail(400, "reference", str(e))


def _int(v):
    return int(v) if v not in (None, "", "null") else None


def _float(v):
    return float(v) if v not in (None, "", "null") else None


def _section(body: dict) -> dict | None:
    sb, eb = _int(body.get("start_bar")), _int(body.get("end_bar"))
    return dict(start_bar=sb, end_bar=eb) if sb or eb else None


def _catalog(fn, *a):
    try:
        return fn(*a)
    except catalog.CatalogError as e:
        fail(400, "catalog", str(e))


# ---------------------------------------------------------------- pages
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/takes/{name}")
def get_take(name: str):
    return FileResponse(take_path(name), media_type="audio/wav")


# ---------------------------------------------------------------- learn: chords, charts, course, progress
@app.get("/api/chords")
def api_chords():
    return dict(groups=catalog.chord_groups(), chords=catalog.chords(), mastered=progress.get()["chords"])


@app.get("/api/charts")
def api_charts():
    """Every chart, with its readiness: the average of its sections' states (0–100)."""
    saved = progress.get()["sections"]
    rows = catalog.charts()
    for r in rows:
        if r.get("error"):
            continue
        st = saved.get(r["id"], {})
        try:
            keys = [s["key"] for s in catalog.chart_sections(catalog.get_chart(r["id"]))]
        except catalog.CatalogError:
            keys = []
        r["readiness"] = progress.section_mastery([st.get(k, {}).get("state", "not_started") for k in keys]) if keys else None
    return rows


@app.get("/api/charts/{cid}")
def api_chart(cid: str):
    try:
        text, mine = catalog.chart_text(cid)
        return dict(id=cid, text=text, mine=mine, chart=catalog.parse_chart(text, cid))
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))


@app.post("/api/charts/validate")
def api_chart_validate(body: dict):
    try:
        c = catalog.parse_chart(body.get("text", ""), "preview")
        return dict(ok=not c["missing"], chart=c, unknown=c["missing"],
                    error=(f"Unknown chords: {', '.join(c['missing'])}" if c["missing"] else None))
    except catalog.CatalogError as e:
        return dict(ok=False, error=str(e))


@app.post("/api/charts")
def api_chart_save(body: dict):
    cid = body.get("id")
    if cid:
        cid = catalog.slug(cid)
    return _catalog(catalog.save_chart, body.get("text", ""), cid)


@app.delete("/api/charts/{cid}")
def api_chart_delete(cid: str):
    _catalog(catalog.delete_chart, cid)
    return dict(ok=True)


def _figure(f: dict) -> dict:
    """A lesson figure. Fretboards get their marks from the theory engine: every scale or chord tone in the
    fret window, labeled with its degree or its (spelled) note name."""
    from .. import theory as th

    if f.get("type") == "staff":                       # notes on the staff: the open strings, or frets on one string
        pos = [(st, 0) for st in (6, 5, 4, 3, 2, 1)] if f.get("notes") == "open" else [(f["string"], fr) for fr in f["frets"]]
        return dict(type="staff", notes=[th.staff_note(th.fret_pitch(st, fr), bool(f.get("flats"))) for st, fr in pos])
    if f.get("type") != "fretboard":
        return f
    lo, hi = f.get("frets", [0, 12])
    tones = th.chord(f["chord"])["tones"] if f.get("chord") else th.scale(f["key"], f["scale"])
    by_pc = {t["pc"]: t for t in tones}
    strings = tuple(f.get("strings", (6, 5, 4, 3, 2, 1)))
    if f.get("path"):                                  # just one playable run (e.g. one octave in one position)
        pos = th.scale_path(f["key"], f["scale"], lo, hi, string=f.get("string"))
    else:
        pos = th.positions(set(by_pc), lo, hi, strings)
    label = "note" if f.get("labels") == "notes" else "degree"
    marks = [dict(string=s, fret=fr, text=by_pc[p % 12][label], kind="root" if by_pc[p % 12]["degree"] == "1" else "tone")
             for s, fr, p in pos]
    return dict(type="fretboard", lo=lo, hi=hi, marks=marks)


def _exercise_extras(e: dict) -> dict:
    """What the UI needs to draw an exercise: tab steps (licks, bends, runs) or chord shapes."""
    out = {}
    steps = catalog.exercise_steps(e)
    if steps is not None:
        out["steps"] = steps
    shapes = catalog.exercise_shapes(e)
    if shapes is not None:
        out["shapes"] = shapes
    return out


# ---------------------------------------------------------------- the daily warm-up
@app.get("/api/warmup")
def api_warmup(drill: str | None = None, key: str | None = None, position: int | None = None, surprise: bool = False):
    """Today's drill (or the one asked for): its notes, its tempo goal and where it sits on the neck."""
    from .. import theory as th
    from .. import warmup

    plan = warmup.surprise() if surprise else warmup.today_plan()
    pick = dict(drill=drill or plan["drill"], key=key or plan["key"], position=plan["position"] if position is None else position)
    if pick["drill"] not in warmup.DRILLS:
        fail(400, "bad_drill", "Unknown drill")
    try:
        th.pc(pick["key"])
    except th.TheoryError:
        fail(400, "bad_key", "Unknown key")
    saved = progress.get()["warmup"]
    info = warmup.DRILLS[pick["drill"]]
    return dict(today=warmup.today_plan(), **pick, steps=warmup.steps(**pick), goal=warmup.goal(saved, pick["drill"]),
                per_beat=info["per_beat"], positions=info["positions"], uses_key=info["uses_key"],
                label=warmup.position_label(pick["drill"], pick["position"]), raise_by=warmup.RAISE, need=warmup.PASS,
                drills=[dict(id=k, goal=warmup.goal(saved, k), best=saved.get(k, {}).get("best"), positions=v["positions"],
                             labels=[warmup.position_label(k, i) for i in range(v["positions"])]) for k, v in warmup.DRILLS.items()])


# ---------------------------------------------------------------- drawn exercises and quizzes
@app.post("/api/exercise/draw")
def exercise_draw(body: dict):
    from .. import quiz

    try:
        ex = catalog.get_exercise(body.get("lesson", ""), body.get("exercise", ""))
        return quiz.draw(body["lesson"], ex, ex.get("min", 80))
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))
    except quiz.QuizError as e:
        fail(400, "quiz", str(e))


@app.post("/api/exercise/check")
def exercise_check(body: dict):
    from .. import quiz

    try:
        return quiz.check(str(body.get("token", "")), int(body.get("index", -1)), body.get("answer"))
    except (quiz.QuizError, ValueError) as e:
        fail(400, "quiz_expired", str(e))


@app.post("/api/exercise/finish")
def exercise_finish(body: dict):
    from .. import quiz

    try:
        r = quiz.finish(str(body.get("token", "")))
    except quiz.QuizError as e:
        fail(400, "quiz_expired", str(e))
    award = progress.exercise_answered(r["lesson"], r["exercise"], r["score"], r["need"])
    award["next"] = catalog.next_step(r["lesson"], r["exercise"], award, progress.get())
    award.pop("progress", None)
    return dict(summary=dict(score=r["score"]), award=award)


@app.post("/api/exercise/variation")
def exercise_variation(body: dict):
    """The exercise a 4th higher (another key or position): what to show; the listener uses it next."""
    from .. import quiz

    try:
        ex = catalog.get_exercise(body.get("lesson", ""), body.get("exercise", ""))
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))
    v = quiz.make_variant(body["lesson"], ex)
    if v is None:
        fail(400, "no_variation", "This exercise doesn't move to another key")
    return dict(label=v["_label"], **_exercise_extras(v))


@app.post("/api/lesson/seen")
def lesson_seen(body: dict):
    try:
        catalog.get_lesson(body.get("lesson", ""))
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))
    progress.mark_seen(body["lesson"])
    return dict(ok=True)


@app.post("/api/lesson/testout")
def lesson_testout(body: dict):
    from .. import quiz

    try:
        ls = catalog.get_lesson(body.get("lesson", ""))
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))
    return quiz.testout_start(ls["id"], ls)


@app.post("/api/lesson/testout/finish")
def lesson_testout_finish(body: dict):
    """Grades the questions of a check. Passing them unlocks the part you play (or completes the lesson
    when there's nothing to play)."""
    from .. import quiz

    try:
        r = quiz.finish(str(body.get("token", "")))
    except quiz.QuizError as e:
        fail(400, "quiz_expired", str(e))
    ok = quiz.testout_answered(r["lesson"], r["score"])
    award = dict(passed=ok, score=r["score"], need=r["need"], xp=0)
    final = next((e["id"] for e in reversed(catalog.get_lesson(r["lesson"])["exercises"]) if e["kind"] not in catalog.ANSWER_KINDS), None)
    if ok and final is None:
        award.update(progress.test_out(r["lesson"]))
    return dict(summary=dict(score=r["score"]), award=award, final=final if ok else None)


@app.get("/api/charts/{cid}/sections")
def chart_sections_get(cid: str):
    try:
        chart = catalog.get_chart(cid)
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))
    saved = progress.get()["sections"].get(cid, {})
    secs = [dict(s, state=saved.get(s["key"], {}).get("state", "not_started"), bpm=saved.get(s["key"], {}).get("bpm"),
                 preset=saved.get(s["key"], {}).get("preset")) for s in catalog.chart_sections(chart)]
    return dict(sections=secs, states=list(progress.SECTION_STATES), mastery=progress.section_mastery([s["state"] for s in secs]))


@app.post("/api/charts/{cid}/sections")
def chart_sections_set(cid: str, body: dict):
    try:
        chart = catalog.get_chart(cid)
    except catalog.CatalogError as e:
        fail(404, "catalog", str(e))
    if body.get("key") not in {s["key"] for s in catalog.chart_sections(chart)}:
        fail(400, "bad_section", "That chart has no such section")
    try:
        progress.set_section(cid, body["key"], body.get("state"), _float(body.get("bpm")), body.get("preset"))
    except ValueError as e:
        fail(400, str(e), "Invalid state or tempo (20–300 BPM)" if str(e) == "bad_bpm" else "Invalid state or tone")
    return chart_sections_get(cid)


def _strums() -> list[dict]:
    return json.loads((catalog.DATA_DIR / "strums.json").read_text(encoding="utf-8"))["patterns"]


@app.get("/api/strums")
def strums():
    return dict(patterns=_strums())


# ---------------------------------------------------------------- ear training (tools, not tied to a lesson)
EAR_KINDS = {"chord_quality": dict(quiz="hear_quality", qualities=["maj", "min", "7", "maj7", "m7", "m7b5"]),
             "chord_basic": dict(quiz="hear_quality", qualities=["maj", "min", "7"]),
             "interval": dict(quiz="interval_ear", intervals=["m3", "M3", "P4", "P5", "m6", "M6", "m7", "P8"])}


CYCLE_MAX, CYCLE_MIN = 200, 8                         # rounds drawn for an interval cycle, rounds that count


@app.post("/api/ear/draw")
def ear_draw(body: dict):
    from .. import quiz

    kind = body.get("kind")
    if kind == "echo":
        d = quiz.draw("__tools__", quiz.TOOLS_ECHO, 75)
        return d
    if kind == "cycle":                               # the interval cycle: a long run, scored on what you heard
        module, mode = body.get("module") or "3-5", body.get("mode") or "melodic"
        if module not in quiz.EAR_MODULES or mode not in ("melodic", "harmonic", "both"):
            fail(400, "bad_kind", "Unknown interval module")
        return quiz.draw("__tools__", dict(id=f"ear-cycle-{module}", kind="quiz", quiz="interval_ear", count=CYCLE_MAX,
                                           intervals=quiz.EAR_MODULES[module], mode=mode, all_choices=True), 80)
    if kind not in EAR_KINDS:
        fail(400, "bad_kind", "Unknown ear-training kind")
    return quiz.draw("__tools__", dict(id=f"ear-{kind}", kind="quiz", count=int(body.get("count") or 10), **EAR_KINDS[kind]), 80)


@app.post("/api/ear/finish")
def ear_finish(body: dict):
    from .. import quiz

    try:
        r = quiz.finish(str(body.get("token", "")), asked_only=bool(body.get("asked_only")))
    except quiz.QuizError as e:
        fail(400, "quiz_expired", str(e))
    kind = r["exercise"].removeprefix("ear-")
    if r["asked"] < CYCLE_MIN and kind.startswith("cycle-"):     # a few rounds aren't a result worth keeping
        return dict(summary=dict(score=r["score"], asked=r["asked"]), award=dict(passed=False, need=80, xp=0, too_short=True))
    award = progress.ear_result(kind, r["score"])
    return dict(summary=dict(score=r["score"], asked=r["asked"]), award=dict(award, passed=r["score"] >= 80, need=80))


# ---------------------------------------------------------------- stats: consistency and tempo over time
@app.get("/api/stats")
def stats():
    """Minutes per day for the last 12 months (rounded to the minute) and, per song or chart practiced with the
    listener, the tempo reached in each session."""
    from datetime import date, timedelta

    days = plan.get_days()
    today = date.today()
    start = today - timedelta(days=364)
    grid = []
    for k in range(365):
        dd = start + timedelta(days=k)
        secs = sum(days.get(dd.isoformat(), {}).values())
        grid.append(dict(date=dd.isoformat(), minutes=round(secs / 60)))
    tempo = []
    for song in history.songs():
        pts = []
        chart_bpm = None
        if (song.get("path") or "").startswith("chart:"):
            try:
                chart_bpm = catalog.get_chart(song["path"][6:])["bpm"]
            except catalog.CatalogError:
                chart_bpm = None
        for s in history.load_sessions(song["id"]):
            bpm, sp = s.get("bpm") or chart_bpm, s.get("final_speed") or s.get("speed")
            score = (s.get("summary") or {}).get("score")
            if sp:
                pts.append(dict(date=(s.get("date") or "")[:10], speed=round(float(sp) * 100), bpm=round(float(bpm) * float(sp)) if bpm else None,
                                score=score))
        if len(pts) >= 1:
            tempo.append(dict(id=song["id"], name=song["name"], points=pts[-60:]))
    songs_played = history.songs()
    return dict(days=grid, tempo=tempo, totals=dict(minutes=sum(g["minutes"] for g in grid),
                                                     active_days=sum(g["minutes"] > 0 for g in grid),
                                                     songs=len(songs_played), sessions=sum(x["sessions"] for x in songs_played),
                                                     streak=progress.get()["streak"]))


@app.get("/api/glossary")
def glossary():
    return json.loads((catalog.DATA_DIR / "glossary.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- theory (tools)
@app.get("/api/theory/scale")
def theory_scale(key: str = "C", name: str = "major"):
    from .. import theory as th

    try:
        return dict(key=key, name=name, notes=th.scale(key, name), scales=list(th.SCALES))
    except th.TheoryError as e:
        fail(400, "theory", str(e))


@app.get("/api/theory/chord")
def theory_chord(symbol: str):
    from .. import theory as th

    try:
        return th.chord(symbol)
    except th.TheoryError as e:
        fail(400, "theory", str(e))


@app.get("/api/theory/voicings")
def theory_voicings(chord: str, kind: str = "triad"):
    from .. import theory as th

    try:
        return dict(chord=th.chord(chord), voicings=th.voicings(chord, kind), kinds=list(th.VOICING_SETS))
    except th.TheoryError as e:
        fail(400, "theory", str(e))


@app.post("/api/theory/name")
def theory_name(body: dict):
    from .. import theory as th

    frets = body.get("frets") or []
    if len(frets) != 6 or any(not isinstance(f, int) or not -1 <= f <= 24 for f in frets):
        fail(400, "bad_frets", "Six frets, from the 6th string to the 1st (-1 = not played)")
    pitches = th.shape_pitches(frets)
    return dict(names=th.name_chord(pitches), notes=[th.plain_name(p) for p in pitches])


@app.post("/api/theory/voice-lead")
def theory_voice_lead(body: dict):
    from .. import theory as th

    prog = [c for c in str(body.get("progression", "")).replace(",", " ").split() if c]
    if not 2 <= len(prog) <= 16:
        fail(400, "bad_progression", "Write 2 to 16 chords, separated by spaces")
    try:
        kind = body.get("kind", "drop2")
        shapes = th.guide_tones(prog) if kind == "guide" else th.voice_lead(prog, kind, body.get("lead", "smooth"))
        return dict(shapes=[dict(name=s["name"], frets=s["frets"]) for s in shapes])
    except th.TheoryError as e:
        fail(400, "theory", str(e))


def _lesson_flow(lid: str, exs: list[dict], p: dict) -> dict:
    """Where you are in the lesson's five steps, and understanding vs playing kept apart.
    discover: you opened it · understand: its quizzes · guided: what you play with help on screen ·
    independent: the same with less help · apply: charts and the exercise in another key."""
    answer = [e for e in exs if e["how"] == "answer"]
    played = [e for e in exs if e["how"] == "play"]
    guided = [e for e in exs if e["stage"] == "guided"]
    fade = [e for e in guided if e["fadeable"]]
    apply = [e for e in exs if e["stage"] == "apply"]
    vary = [e for e in exs if e["can_vary"]]
    seen = lid in p["seen"] or any(e["best"] is not None for e in exs)
    steps = dict(
        discover=seen,
        understand=all(e["passed"] for e in answer) if answer else seen,
        guided=all(e["passed"] for e in guided) if guided else all(e["passed"] for e in played),
        independent=all((e["guidance"] or 0) >= 1 for e in fade) if fade else all(e["passed"] for e in played),
        apply=(all(e["passed"] for e in apply) if apply else True) and (any(e["varied"] for e in vary) if vary else True),
    )
    return dict(flow=[dict(step=s, done=steps[s]) for s in catalog.STAGES],
                understood=dict(done=sum(e["passed"] for e in answer), total=len(answer)),
                played=dict(done=sum(e["passed"] for e in played), total=len(played)))


@app.get("/api/course")
def api_course():
    p = progress.get()
    levels = []
    for lvl in catalog.course()["levels"]:
        ls = []
        for x in lvl["lessons"]:
            exs = []
            for e in x["exercises"]:
                key = f"{x['id']}/{e['id']}"
                exs.append(dict(e, best=p["exercises"].get(key), passed=p["exercises"].get(key, -1) >= e.get("min", 80),
                                how="answer" if e["kind"] in catalog.ANSWER_KINDS else "play", stage=catalog.exercise_stage(e),
                                fadeable=e["kind"] in catalog.FADEABLE, guidance=p["guidance"].get(key),
                                can_vary=catalog.variation(e) is not None,
                                varied=p["variations"].get(key, -1) >= e.get("min", 80), **_exercise_extras(e)))
            ls.append(dict(x, exercises=exs, chords=catalog.lesson_chords(x), figures=[_figure(f) for f in x.get("figures", [])],
                           done=x["id"] in p["lessons"], pinned=p["tutorials"].get(x["id"]),
                           tested_out=x["id"] in p["tested_out"], **_lesson_flow(x["id"], exs, p)))
        levels.append(dict(lvl, lessons=ls))
    nxt = next((x for lv in levels for x in lv["lessons"] if not x["done"]), None)
    return dict(levels=levels, next=nxt and dict(id=nxt["id"], title=nxt["title"]))


@app.get("/api/progress")
def api_progress():
    return progress.get()


@app.post("/api/progress/chord")
def api_progress_chord(body: dict):
    via = body.get("via")
    if via not in ("ear", "camera") or catalog.get_chord(body.get("chord", "")) is None:
        fail(400, "bad_chord", "Invalid chord or method")
    return progress.chord_mastered(body["chord"], via)


@app.post("/api/progress/tutorial")
def api_progress_tutorial(body: dict):
    url = (body.get("url") or "").strip() or None
    if url and not url.startswith(("https://", "http://")):
        fail(400, "bad_url", "Paste a link starting with https://")
    _catalog(catalog.get_lesson, body.get("lesson", ""))
    return progress.pin_tutorial(body["lesson"], url)


# ---------------------------------------------------------------- status / settings
@app.get("/api/settings/sources")
def settings_sources():
    """Where each setting's value comes from: the environment, what you saved, auto-detected, or the default."""
    import os

    saved = config.load()
    audio, inst = saved.get("audio", {}), saved.get("instrument", {})
    src = lambda d, k, auto=False: "saved" if d.get(k) is not None else ("auto" if auto else "default")
    return dict(
        home=dict(value=str(config.HOME), source="env" if os.environ.get("GUITARR_HOME") else "default", env="GUITARR_HOME"),
        device=dict(value=audio_settings().get("device"), source=src(audio, "device", auto=True)),
        channel=dict(value=audio_settings().get("channel"), source=src(audio, "channel")),
        output_device=dict(value=audio.get("output_device"), source=src(audio, "output_device", auto=True)),
        latency_ms=dict(value=audio.get("latency_ms") or 0, source=src(audio, "latency_ms")),
        tuning=dict(value=config.instrument()["tuning"], source=src(inst, "tuning")),
        left_handed=dict(value=config.instrument()["left_handed"], source=src(inst, "left_handed")),
    )


@app.get("/api/status")
def status():
    return dict(version=__version__, home=str(config.HOME),
                live=bool(S.session and S.session.running), tuner=S.tuner is not None)


@app.get("/api/devices")
def api_devices():
    try:
        return devices()
    except AudioError as e:
        return dict(inputs=[], outputs=[], suggested=None, error=str(e))


@app.get("/api/config")
def get_config():
    return dict(audio=audio_settings(), saved=config.load()["audio"], path=str(config.CONFIG_PATH))


@app.post("/api/config")
def set_config(body: dict):
    audio = {k: body.get(k) for k in config.AUDIO_KEYS}
    for k in ("channel", "samplerate"):
        audio[k] = _int(audio[k])
    for k in ("latency_ms", "gate_db", "sensitivity"):
        audio[k] = _float(audio[k])
    for k in ("device", "output_device"):
        if audio[k] in ("", None):
            audio[k] = None
        elif str(audio[k]).lstrip("-").isdigit():
            audio[k] = int(audio[k])
    data = config.load()
    for k, v in audio.items():
        if v is None:
            data["audio"].pop(k, None)
        else:
            data["audio"][k] = v
    config.save(data)
    return get_config()


# ---------------------------------------------------------------- today's practice
@app.get("/api/today")
def api_today():
    return routine.build()


@app.post("/api/today/budget")
def api_today_budget(body: dict):
    """How much time you have today (15, 30, 60 or 120 minutes, or none): the plan is rebuilt to fit."""
    m = body.get("minutes")
    try:
        progress.set_budget(None if m in (None, "", 0) else int(m))
    except (ValueError, TypeError):
        fail(400, "bad_budget", "Pick 15, 30, 60 or 120 minutes")
    return routine.build()


@app.post("/api/today/queue")
def api_today_queue(body: dict):
    """Pins a section of a chart ("chart:<id>") or a song ("song:<name>") to today's plan."""
    ref, section = str(body.get("ref") or ""), str(body.get("section") or "")
    if not ref.startswith(("chart:", "song:")) or not section:
        fail(400, "bad_queue", "Pick a chart or song section")
    try:
        progress.queue_add(ref, section)
    except ValueError:
        fail(400, "queue_full", f"Today's queue holds up to {progress.QUEUE_MAX} sections: clear some first")
    return routine.build()


@app.delete("/api/today/queue")
def api_today_queue_clear(ref: str | None = None, section: str | None = None):
    progress.queue_remove(ref, section)
    return routine.build()


@app.post("/api/today/check")
def api_today_check(body: dict):
    step = str(body.get("step") or "")
    if step != "tune":
        fail(400, "bad_step", "Only steps that can't be detected can be ticked")
    progress.check_step(step, bool(body.get("done", True)))
    return routine.build()


# ---------------------------------------------------------------- instrument (tuning, handedness)
@app.get("/api/instrument")
def api_instrument():
    from ..core import TUNINGS
    inst = config.instrument()
    return {**inst, "strings": config.instrument_tuning(), "tunings": {k: v for k, v in TUNINGS.items()}}


@app.put("/api/instrument")
def api_instrument_set(body: dict):
    from ..core import TUNINGS
    tuning = body.get("tuning")
    if tuning is not None and tuning not in TUNINGS:
        fail(400, "bad_tuning", "Unknown tuning")
    lefty = body.get("left_handed")
    config.save_instrument(tuning=tuning, left_handed=None if lefty is None else bool(lefty))
    return api_instrument()


# ---------------------------------------------------------------- daily reminder
@app.get("/api/reminder")
def api_reminder():
    r = reminder.get()
    return {**r, "due": reminder.due(cfg=r)}


@app.put("/api/reminder")
def api_reminder_set(body: dict):
    try:
        return reminder.update(body.get("enabled"), body.get("time"), body.get("title"), body.get("body"))
    except reminder.ReminderError as e:
        fail(400, e.code, str(e))


@app.post("/api/reminder/shown")
def api_reminder_shown():
    """The page showed the reminder as a browser notification (no desktop notifier)."""
    reminder.mark_sent()
    return dict(ok=True)


@app.post("/api/reminder/test")
def api_reminder_test():
    r = reminder.get()
    sent = reminder.notify(r["title"], r["body"].replace("{left}", "0:15"))
    return dict(desktop=sent)


# ---------------------------------------------------------------- backup
MAX_UPLOAD = 1024 ** 3


@app.get("/api/backup")
def api_backup(takes: bool = False):
    return Response(backup.create(takes), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{backup.filename()}"'})


@app.post("/api/backup")
async def api_restore(file: UploadFile = File(...)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        fail(400, "backup_too_big", "The backup is too big")
    with S.lock:
        if S.session and S.session.running:
            fail(409, "busy", "Stop practicing first")
        try:
            return backup.restore(data)
        except backup.BackupError as e:
            fail(400, e.code, str(e))


# ---------------------------------------------------------------- practice plan
def _plan(fn, *a):
    try:
        return fn(*a)
    except plan.PlanError as e:
        fail(400, e.code, str(e))


@app.get("/api/plan")
def api_plan():
    return plan.get()


@app.put("/api/plan/goal")
def api_plan_goal(body: dict):
    return _plan(plan.set_weekly_goal, body.get("weekly_minutes"))


@app.put("/api/plan/categories/{cid}")
def api_plan_minutes(cid: str, body: dict):
    return _plan(plan.set_minutes, cid, body.get("minutes"))


@app.post("/api/plan/categories")
def api_plan_add(body: dict):
    return _plan(plan.add_category, body.get("name"), body.get("minutes"))


@app.delete("/api/plan/categories/{cid}")
def api_plan_remove(cid: str):
    return _plan(plan.remove_category, cid)


@app.post("/api/plan/free")
def api_plan_free(body: dict):
    if S.session and S.session.running:          # the listening session already counts this time
        return dict(counted=0.0)
    return dict(counted=_plan(plan.record_free_play, body.get("seconds")))


@app.post("/api/plan/timer")
def api_plan_timer(body: dict):
    return _plan(plan.timer, str(body.get("action") or ""), body.get("category"))


# ---------------------------------------------------------------- tone rig (amp, pedals…)
def _rig(fn, *a):
    try:
        return fn(*a)
    except rig.RigError as e:
        fail(400, e.code, str(e))


@app.get("/api/rig")
def api_rig():
    return rig.get()


@app.put("/api/rig/current")
def api_rig_current(body: dict):
    _rig(rig.save_current, body.get("rig"))
    return dict(ok=True)


@app.post("/api/rig/presets")
def api_rig_preset_save(body: dict):
    return _rig(rig.save_preset, body.get("name"), body.get("rig"))


@app.get("/api/rig/irs")
def api_rig_irs():
    return rig.list_irs()


@app.post("/api/rig/irs")
async def api_rig_ir_upload(file: UploadFile = File(...)):
    data = await file.read(rig.IR_MAX_BYTES + 1)
    return _rig(rig.save_ir, file.filename, data)


@app.get("/api/rig/irs/{name}")
def api_rig_ir(name: str):
    return FileResponse(_rig(rig.ir_path, name))


@app.delete("/api/rig/irs/{name}")
def api_rig_ir_delete(name: str):
    _rig(rig.delete_ir, name)
    return dict(ok=True)


@app.post("/api/rig/capture")
async def rig_capture(di: UploadFile = File(...), amp: UploadFile = File(...)):
    """Fits the capture pedal from a direct recording and the same playing through an amp (experimental)."""
    import io

    import soundfile as sf

    from .. import capture

    try:
        x, sr_x = sf.read(io.BytesIO(await di.read(50 * 1024 * 1024)))
        y, sr_y = sf.read(io.BytesIO(await amp.read(50 * 1024 * 1024)))
    except Exception:
        fail(400, "bad_audio", "Both files must be audio recordings (WAV, FLAC or OGG)")
    try:
        return capture.fit(x, y, sr_x, sr_y)
    except capture.CaptureError as e:
        fail(400, f"capture_{e}", {"too_short": "Record at least half a second of playing",
                                    "silent": "One of the recordings is silent"}.get(str(e), str(e)))


@app.delete("/api/rig/presets/{pid}")
def api_rig_preset_delete(pid: str):
    if not rig.delete_preset(pid):
        fail(404, "no_preset", "Preset not found")
    return dict(ok=True)


# ---------------------------------------------------------------- songs
@app.get("/api/songs")
def songs():
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    presets = config.load()["songs"]
    out = []
    saved = progress.get()["sections"]
    for p in sorted(config.SONGS_DIR.iterdir(), key=lambda p: -p.stat().st_mtime):
        if p.suffix.lower() in REFERENCE_EXT:
            st = saved.get(f"song:{p.name}", {})
            readiness = None
            if st:                                    # only songs you've started tracking: reading every file is slow
                keys = [s["key"] for s in _song_sections(p.name)]
                readiness = progress.section_mastery([st.get(k, {}).get("state", "not_started") for k in keys])
            out.append(dict(name=p.name, ext=p.suffix.lower(), preset=presets.get(p.name, {}), readiness=readiness))
    return out


def _song_sections(name: str) -> list[dict]:
    """A song's sections from its file (Guitar Pro markers); without markers, the whole song is one section."""
    from .. import songfacts

    f = songfacts.facts(song_path(name))
    return f["sections"] or [{"name": "Whole song", "key": "Whole song", "from": 1, "to": None}]


@app.get("/api/songs/{name}/facts")
def song_facts(name: str):
    from .. import songfacts

    p = song_path(name)
    f = songfacts.facts(p)
    q = " ".join(x for x in [f.get("title"), f.get("artist")] if x)
    return dict(f, name=name, video=progress.get()["tutorials"].get(f"song:{name}"),
                searches=dict(lesson=f"{q} guitar lesson", backing=f"{q} backing track", guitar=f"{q} guitar only"))


@app.get("/api/songs/{name}/sections")
def song_sections_get(name: str):
    saved = progress.get()["sections"].get(f"song:{name}", {})
    secs = [dict(s, state=saved.get(s["key"], {}).get("state", "not_started"), bpm=saved.get(s["key"], {}).get("bpm"),
                 preset=saved.get(s["key"], {}).get("preset")) for s in _song_sections(name)]
    return dict(sections=secs, states=list(progress.SECTION_STATES), mastery=progress.section_mastery([s["state"] for s in secs]))


@app.post("/api/songs/{name}/sections")
def song_sections_set(name: str, body: dict):
    if body.get("key") not in {s["key"] for s in _song_sections(name)}:
        fail(400, "bad_section", "That song has no such section")
    try:
        progress.set_section(f"song:{name}", body["key"], body.get("state"), _float(body.get("bpm")), body.get("preset"))
    except ValueError as e:
        fail(400, str(e), "Invalid state or tempo (20–300 BPM)" if str(e) == "bad_bpm" else "Invalid state or tone")
    return song_sections_get(name)


@app.post("/api/songs/{name}/video")
def song_video(name: str, body: dict):
    """Pins (or clears, with an empty url) a video for a song."""
    song_path(name)
    url = str(body.get("url") or "").strip()
    if url and not url.startswith(("http://", "https://")):
        fail(400, "bad_url", "A link starts with http:// or https://")
    progress.pin_tutorial(f"song:{name}", url or None)
    return dict(video=url or None)


# ---------------------------------------------------------------- setlists
def _setlist_view(s: dict) -> dict:
    from .. import setlists

    saved = progress.get()["sections"]
    items = []
    for it in s["items"]:
        row = dict(it, tuning=setlists.tuning_of(it))
        if it["kind"] == "chart":
            try:
                c = catalog.get_chart(it["id"])
                keys = [x["key"] for x in catalog.chart_sections(c)]
                st = saved.get(it["id"], {})
                row.update(title=c["title"], bpm=c["bpm"], exists=True,
                           readiness=progress.section_mastery([st.get(k, {}).get("state", "not_started") for k in keys]) if keys else None)
            except catalog.CatalogError:
                row.update(title=it["id"], exists=False)
        else:
            p = config.SONGS_DIR / _safe_name(it["id"])
            st = saved.get(f"song:{it['id']}", {})
            keys = [x["key"] for x in _song_sections(it["id"])] if st and p.exists() else []
            row.update(title=it["id"], exists=p.exists(),
                       readiness=progress.section_mastery([st.get(k, {}).get("state", "not_started") for k in keys]) if keys else None)
        items.append(row)
    return dict(s, items=items, warnings=setlists.warnings(s["items"]))


@app.get("/api/setlists")
def setlists_all():
    from .. import setlists

    return [_setlist_view(s) for s in setlists.all_lists()]


@app.post("/api/setlists")
def setlists_create(body: dict):
    from .. import setlists

    try:
        return _setlist_view(setlists.create(body.get("name", "")))
    except setlists.SetlistError as e:
        fail(400, str(e), {"empty_name": "Give the setlist a name", "long_name": "Use 80 characters or fewer",
                            "duplicate_name": "There's already a setlist with that name"}.get(str(e), str(e)))


@app.get("/api/setlists/{sid}")
def setlists_get(sid: str):
    from .. import setlists

    try:
        return _setlist_view(setlists.get(sid))
    except setlists.SetlistError as e:
        fail(404, str(e), "Setlist not found")


@app.put("/api/setlists/{sid}")
def setlists_update(sid: str, body: dict):
    from .. import setlists

    try:
        return _setlist_view(setlists.update(sid, body.get("items"), body.get("name")))
    except setlists.SetlistError as e:
        fail(404 if str(e) == "no_setlist" else 400, str(e), "Setlist not found" if str(e) == "no_setlist" else "Invalid setlist")


@app.delete("/api/setlists/{sid}")
def setlists_delete(sid: str):
    from .. import setlists

    try:
        setlists.delete(sid)
    except setlists.SetlistError as e:
        fail(404, str(e), "Setlist not found")
    return dict(ok=True)


@app.post("/api/songs")
async def upload_song(file: UploadFile = File(...)):
    from ..importers import MAX_BYTES, looks_like_tab

    name = _safe_name(file.filename)
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    if Path(name).suffix.lower() == ".txt":                # a text tab: keep it as .tab
        text = (await file.read(MAX_BYTES + 1)).decode("utf-8", errors="replace")
        if not looks_like_tab(text):
            fail(400, "bad_format", "That text file doesn't look like a tablature")
        name = Path(name).stem + ".tab"
        (config.SONGS_DIR / name).write_text(text, encoding="utf-8")
        return dict(name=name)
    if Path(name).suffix.lower() not in REFERENCE_EXT:
        fail(400, "bad_format", "Unsupported format: upload MIDI, Guitar Pro, MusicXML, a text tab or audio")
    with open(config.SONGS_DIR / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return dict(name=name)


@app.post("/api/demo")
def make_demo():
    from ..demo import main as demo_main

    out = demo_main(config.HOME / "demo")
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(out / "reference.mid", config.SONGS_DIR / "demo-reference.mid")
    shutil.copy(out / "take.wav", config.TAKES_DIR / "demo-take.wav")
    return dict(song="demo-reference.mid", take="demo-take.wav")


@app.get("/api/songs/{name}/tracks")
def tracks(name: str):
    try:
        return list_tracks(song_path(name))
    except HTTPException:
        raise
    except Exception as e:
        fail(400, "reference", str(e))


@app.post("/api/preview")
def preview(body: dict):
    ref = ref_from(body)
    g = ref.grid
    last_bar = g.bar_index(max(n.start for n in ref.notes))
    first_bar = g.bar_index(ref.notes[0].start)
    return dict(
        name=ref.name, track=ref.track, tuning=ref.tuning, first_bar=first_bar, last_bar=last_bar,
        notes=[dict(s=round(n.start, 3), e=round(n.end, 3), p=n.pitch, string=n.string, fret=n.fret, label=n.label)
               for n in ref.notes],
        downbeats=[round(g.bar_time(b), 3) for b in range(first_bar, last_bar + 2)],
        bpm=round(60 / g.beat_len(ref.notes[0].start), 1),
    )


@app.post("/api/presets")
def save_preset(body: dict):
    song = _safe_name(body.pop("song"))
    kw = {k: body.get(k) for k in config.SONG_KEYS}
    for k in ("transpose", "start_bar", "end_bar", "beats_per_bar"):
        kw[k] = _int(kw[k])
    for k in ("speed", "bpm", "first_beat"):
        kw[k] = _float(kw[k])
    kw["track"] = kw["track"] or None
    data = config.load()
    data["songs"][song] = {k: v for k, v in kw.items() if v is not None}
    config.save(data)
    return data["songs"][song]


# ---------------------------------------------------------------- takes / analysis
@app.get("/api/takes")
def takes():
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    return [dict(name=p.name, size=p.stat().st_size, mtime=p.stat().st_mtime)
            for p in sorted(config.TAKES_DIR.glob("*.wav"), key=lambda p: -p.stat().st_mtime)]


def _store_take(file: UploadFile) -> str:
    name = _safe_name(file.filename)
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.TAKES_DIR / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return name


@app.post("/api/takes")
async def upload_take(file: UploadFile = File(...)):
    return dict(name=_store_take(file))


@app.post("/api/analyze")
def analyze(options: str = Form(...), take: UploadFile | None = File(None)):
    from ..analysis import FileOptions, analyze_take

    body = json.loads(options)
    tpath = take_path(_store_take(take)) if take is not None and take.filename else take_path(body["take"])
    ref = ref_from(body)
    msgs: list[str] = []
    try:
        res, _ = analyze_take(ref, tpath, FileOptions(
            transpose=_int(body.get("transpose")) or 0,
            timing_tol=(_float(body.get("timing_tol_ms")) or 60) / 1000), log=msgs.append)
    except (ReferenceError, ValueError) as e:
        fail(400, "analysis", str(e))
    res["messages"] = [m.strip() for m in msgs if m.strip().startswith("⚠")]
    res["take_name"] = tpath.name
    history.save(res, _section(body))
    res["award"] = dict(xp=progress.add_practice(res["summary"].get("score"), "take_analysis"))
    return res


# ---------------------------------------------------------------- live
@app.post("/api/live/start")
def live_start(body: dict):
    from ..session import LiveOptions, LiveSession

    with S.lock:
        if S.session and S.session.running:
            fail(409, "busy", "A session is already running")
        if S.tuner:
            S.tuner.stop()
        ropts, ctx = ref_options(body)
        if not body.get("simulate"):
            plan.pause_timer()          # the session counts its own time
        try:
            ref = load_reference(ropts, log=lambda m: None)
        except ReferenceError as e:
            fail(400, "reference", str(e))
        a = audio_settings()
        sim = take_path(body["simulate"]) if body.get("simulate") else None
        mode = ctx.get("mode") or body.get("mode", "wait")
        speed = ctx.get("speed") or _float(body.get("speed")) or 1.0
        chart = ropts.chart is not None
        opts = LiveOptions(
            mode=mode, speed=speed,
            device=a.get("device"), channel=a.get("channel") or 1, output_device=a.get("output_device"),
            samplerate=a.get("samplerate"), click=body.get("click", True),
            count_in=_int(body.get("count_in")), latency_ms=a.get("latency_ms") or 0.0,
            gate_db=a["gate_db"] if a.get("gate_db") is not None else -50.0,
            sensitivity=a.get("sensitivity") or 1.0, loop=bool(body.get("loop")) and ctx["type"] == "practice",
            trainer=bool(body.get("trainer")) and mode == "tempo" and ctx["type"] == "practice",
            speed_step=(_float(body.get("speed_step")) or 5) / 100, target=_float(body.get("target")) or 90,
            max_speed=(_float(body.get("max_speed")) or 100) / 100,
            legato=body.get("legato", not chart) and not chart,
            count_extras=not chart, transpose=_int(body.get("transpose")) or 0,
            simulate=sim, fast=bool(body.get("fast")) and sim is not None,
            backing=bool(body.get("backing")) and chart, hold=ctx.get("hold", 1.0),
            hum_hz=None if sim else a.get("hum_hz"),
            # swing is felt, not measured: a swung chart gets a wider timing window
            timing_tol=0.09 if chart and (ropts.chart or {}).get("swing") else 0.06,
        )
        try:
            sess = LiveSession(ref, opts)
        except AudioError as e:
            fail(400, "audio", str(e))
        S.session, S.section, S.ctx, S.final = sess, _section(body), ctx, None

        def run():
            try:
                rep = sess.run()
                if ctx["type"] == "practice" and rep["summary"]["judged"] and not opts.simulate:
                    history.save(rep, S.section)
                rep["award"] = progress.on_session(ctx, rep)
                if ctx and ctx.get("type") == "exercise":
                    rep["award"]["next"] = catalog.next_step(ctx["lesson"], ctx["exercise"], rep["award"], progress.get())
                rep["award"]["practice_s"] = plan.record_session(ctx, rep)
                rep["context"] = ctx
                S.final = rep
            except Exception as e:  # kept in sess.error for the UI
                sess.error = sess.error or str(e)

        S.thread = threading.Thread(target=run, daemon=True)
        S.thread.start()
        if ctx["type"] == "drill":  # the chord-change minute stops by itself
            threading.Timer(ctx["seconds"] + 1.5, sess.stop).start()
    return dict(ok=True, events=len(sess.events), context=ctx,
                grid_bpm=round(60 / ref.grid.beat_len(ref.notes[0].start), 1))


@app.post("/api/live/hint")
def live_hint():
    """A hint for the note or chord you're on: where to play it. Each request is counted with the result."""
    sess, ctx = S.session, S.ctx
    if not sess or not ctx or ctx.get("type") != "exercise":
        fail(404, "no_session", "No exercise is listening")
    ctx["hints"] = ctx.get("hints", 0) + 1
    snap = sess.snapshot()
    cur = next((e for e in snap["lane"] if e["current"]), None)
    if cur is None:
        return dict(hints=ctx["hints"], hint=None)
    tab = [list(x) for x in cur.get("tab") or []]
    return dict(hints=ctx["hints"], hint=dict(label=cur["label"], tab=tab))


@app.post("/api/live/stop")
def live_stop():
    sess, th = S.session, S.thread
    if not sess:
        fail(404, "no_session", "No session")
    sess.stop()
    if th:
        th.join(5)
    return dict(report=S.final or sess.report, error=sess.error)


@app.get("/api/live/state")
def live_state():
    if not S.session:
        return dict(active=False)
    return dict(active=True, state=S.session.snapshot(), report=S.final, context=S.ctx)


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    sent = None
    try:
        while True:
            sess = S.session
            if sess is not None:
                await ws.send_json(dict(type="state", state=sess.snapshot(), context=S.ctx))
                if S.final is not None and sent is not S.final:
                    sent = S.final
                    await ws.send_json(dict(type="report", report=S.final))
                if sess.error and not sess.running:
                    await ws.send_json(dict(type="error", error=sess.error))
            await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError):
        pass


# ---------------------------------------------------------------- tuner
@app.websocket("/ws/tuner")
async def ws_tuner(ws: WebSocket):
    from ..tuner import Tuner

    await ws.accept()
    if S.session and S.session.running:
        await ws.send_json(dict(error=dict(code="busy", message="Stop practicing to use the tuner.")))
        await ws.close()
        return
    try:
        sim = ws.query_params.get("simulate")
        a = audio_settings()
        # `device` / `channel` let the setup wizard and settings test an input before saving it.
        dev = ws.query_params.get("device")
        device = (int(dev) if dev.lstrip("-").isdigit() else dev) if dev else a.get("device")
        channel = _int(ws.query_params.get("channel")) or a.get("channel") or 1
        samplerate = a.get("samplerate") if dev is None else None
        src = FileSource(take_path(sim)) if sim else MicSource(device, channel, samplerate)
    except HTTPException as e:
        await ws.send_json(dict(error=e.detail))
        await ws.close()
        return
    except (AudioError, ValueError) as e:
        await ws.send_json(dict(error=dict(code="audio", message=str(e))))
        await ws.close()
        return
    tuner = Tuner(src, tuning=config.instrument_tuning(), hum_hz=a.get("hum_hz"))
    S.tuner = tuner
    th = threading.Thread(target=tuner.run, daemon=True)
    th.start()
    try:
        await ws.send_json(dict(source=src.name))
        while th.is_alive():
            await ws.send_json(tuner.reading)
            await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        tuner.stop()
        if S.tuner is tuner:
            S.tuner = None


# ---------------------------------------------------------------- signal check
def _input_source(ws_params) -> MicSource:
    a = audio_settings()
    dev = ws_params.get("device")
    device = (int(dev) if dev.lstrip("-").isdigit() else dev) if dev else a.get("device")
    channel = _int(ws_params.get("channel")) or a.get("channel") or 1
    return MicSource(device, channel, a.get("samplerate") if dev is None else None)


@app.websocket("/ws/signal")
async def ws_signal(ws: WebSocket):
    """Live input levels for the signal check; the last seconds are kept for the measurements."""
    await ws.accept()
    if (S.session and S.session.running) or S.tuner:
        await ws.send_json(dict(error=dict(code="busy", message="Stop practicing or tuning first.")))
        await ws.close()
        return
    try:
        sim = ws.query_params.get("simulate")            # a recorded take instead of the input (tests, demos)
        src = FileSource(take_path(sim)) if sim else _input_source(ws.query_params)
    except HTTPException as e:
        await ws.send_json(dict(error=e.detail))
        await ws.close()
        return
    except (AudioError, ValueError) as e:
        await ws.send_json(dict(error=dict(code="audio", message=str(e))))
        await ws.close()
        return
    probe = signalcheck.Probe(src)
    S.probe, S.signal = probe, {}
    th = threading.Thread(target=probe.run, daemon=True)
    th.start()
    try:
        await ws.send_json(dict(source=src.name, sr=src.sr))
        while th.is_alive():
            await ws.send_json(probe.reading)
            await asyncio.sleep(signalcheck.LEVEL_EVERY)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        probe.stop()          # it stops listening but keeps its last seconds for the measurements


@app.post("/api/signal/measure")
def api_signal_measure(body: dict):
    """Analyzes the last `seconds` of input for one step: silence | strum | notes."""
    probe = S.probe
    if probe is None:
        fail(409, "no_probe", "The signal check isn't listening")
    step = body.get("step")
    seconds = min(max(_float(body.get("seconds")) or 4, 1), signalcheck.BUFFER_S)
    y = probe.last(seconds)
    if len(y) < probe.sr * 0.8:
        fail(400, "too_short", "Not enough audio yet")
    if step == "silence":
        r = signalcheck.analyze_silence(y, probe.sr)
    elif step == "strum":
        r = signalcheck.analyze_strum(y, probe.sr)
    elif step == "notes":
        sil = S.signal.get("silence", {}).get("result", {})
        r = signalcheck.analyze_notes(y, probe.sr, int(body.get("expected") or 6), config.instrument_tuning(),
                                      sil.get("floor_db"), sil.get("hum_hz"))
    else:
        fail(400, "bad_step", "Unknown step")
    S.signal[step] = dict(result=r, audio=y, sr=probe.sr)
    return r


@app.get("/api/signal/clip/{step}")
def api_signal_clip(step: str):
    """The audio of a step, to hear what guitarr heard."""
    got = S.signal.get(step)
    if not got:
        fail(404, "no_clip", "Nothing recorded for that step yet")
    return Response(signalcheck.wav_bytes(got["audio"], got["sr"]), media_type="audio/wav")


@app.post("/api/signal/apply")
def api_signal_apply(body: dict):
    """Saves what the check found: noise gate, sensitivity and the hum filter."""
    keys = {}
    if body.get("gate_db") is not None:
        keys["gate_db"] = max(-90.0, min(-20.0, float(body["gate_db"])))
    if body.get("sensitivity") is not None:
        keys["sensitivity"] = max(0.3, min(3.0, float(body["sensitivity"])))
    data = config.load()
    data["audio"].update(keys)
    hum = body.get("hum_hz")
    if hum in (50, 60):
        data["audio"]["hum_hz"] = hum
    elif "hum_hz" in body:
        data["audio"].pop("hum_hz", None)
    config.save(data)
    return dict(audio=audio_settings())


# ---------------------------------------------------------------- calibration
@app.post("/api/calibrate")
def calibrate_start(body: dict | None = None):
    from ..tuner import calibrate

    if S.calib.get("running"):
        fail(409, "busy", "Calibration already running")
    if S.session and S.session.running:
        fail(409, "busy", "Stop practicing first")
    a = audio_settings()
    bpm = _float((body or {}).get("bpm")) or 90
    S.calib = dict(running=True, beat=0, total=16, warmup=True, result=None)

    def prog(p):
        S.calib.update(p)

    def run():
        try:
            r = calibrate(a.get("device"), a.get("channel") or 1, a.get("output_device"), bpm=bpm,
                          on_progress=prog)
            if r["ok"]:
                config.update_audio(latency_ms=r["latency_ms"])
        except Exception as e:
            r = dict(ok=False, code="error", message=str(e))
        S.calib.update(running=False, result=r)

    threading.Thread(target=run, daemon=True).start()
    return S.calib


@app.get("/api/calibrate")
def calibrate_state():
    return S.calib


# ---------------------------------------------------------------- history
@app.get("/api/history")
def api_history():
    return history.songs()


@app.get("/api/history/{sid}")
def api_history_song(sid: str):
    sid = _safe_name(sid)
    sessions = history.load_sessions(sid)
    if not sessions:
        fail(404, "no_sessions", "No sessions")
    light = [dict(file=s["file"], date=s.get("date"), kind=s.get("kind"), score=history.session_score(s),
                  speed=s.get("final_speed") or s.get("speed"), section=s.get("section"),
                  mode=s.get("mode"), summary=s.get("summary"), passes=s.get("passes", []))
             for s in sessions]
    ref = sessions[-1].get("reference", {})
    rpath = ref.get("path", "") or ""
    if rpath.startswith("chart:"):
        song = rpath
    else:
        song = Path(rpath).name if rpath and (config.SONGS_DIR / Path(rpath).name).exists() else None
    return dict(id=sid, reference=ref, song=song, sessions=light, problem_bars=history.problem_bars(sessions))


# ---------------------------------------------------------------- startup
def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://{host}:{port}/"
    print(f"guitarr {__version__} — open {url}  (Ctrl+C to quit)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    reminder.start_loop()
    uvicorn.run(app, host=host, port=port, log_level="warning")
