"""Aprender: diccionario, cifrados (formato propio), ruta con ejercicios por escucha,
progreso (XP, racha, récords) y su API."""
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


# ---------------------------------------------------------------- contenido
def test_chord_dictionary_is_consistent():
    chords = catalog.chords()
    assert len(chords) >= 35
    for c in chords:
        assert len(c["frets"]) == 6 and len(c["fingers"]) == 6
        pcs = {NAMES[(catalog.OPEN_STRINGS[i] + f) % 12] for i, f in enumerate(c["frets"]) if f >= 0}
        assert pcs == set(c["notes"]), c["id"]


def test_builtin_cifrados_parse_and_use_known_chords():
    rows = catalog.cifrados()
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


CIFRADO = """titulo: Prueba
bpm: 100
compas: 3/4
capo: 1
rasgueo: D.DU.U

[A]
Am | % | C G | -   # comentario
[B]
E7 | Am
"""


def test_parse_cifrado_format():
    c = catalog.parse_cifrado(CIFRADO, "prueba")
    assert c["title"] == "Prueba" and c["bpm"] == 100 and c["beats_per_bar"] == 3 and c["capo"] == 1
    assert [(b["chord"], b["beats"]) for b in c["bars"]] == [
        ("Am", 3), ("Am", 3), ("C", 1.5), ("G", 1.5), (None, 3), ("E7", 3), ("Am", 3)]
    assert c["bars"][0]["section"] == "A" and c["bars"][5]["section"] == "B"
    ref = load_reference(RefOptions(chart=c), log=lambda m: None)
    starts = sorted({n.start for n in ref.notes})
    assert len(starts) == 6                        # el compás "-" no suena
    assert ref.grid.bar_of(starts[2]) == (3, 1.0) and ref.grid.bar_of(starts[3]) == (3, 2.5)
    assert ref.capo == 1 and {n.label for n in ref.notes} == {"Am", "C", "G", "E7"}


@pytest.mark.parametrize("text,err", [
    ("titulo: x\n", "no tiene compases"),
    ("% | G\n", "'%' sin un acorde"),
    ("compas: 13/4\nG\n", "compás inválido"),
    ("bpm: 5\nG | D\n", "bpm"),
])
def test_parse_cifrado_errors(text, err):
    with pytest.raises(catalog.CatalogError, match=err):
        catalog.parse_cifrado(text)


def test_user_cifrados_save_list_delete():
    with pytest.raises(catalog.CatalogError, match="No conozco"):
        catalog.save_cifrado("titulo: Raro\nH7 | G\n")
    r = catalog.save_cifrado("titulo: Mi Canción!\nG | D\n")
    assert r["id"] == "mi-canción"
    mine = [c for c in catalog.cifrados() if c["mine"]]
    assert [c["id"] for c in mine] == ["mi-canción"]
    dup = catalog.save_cifrado(catalog.cifrado_text("03-pop-sol")[0], "03-pop-sol")
    assert dup["id"] == "03-pop-sol-mio"          # nunca pisa un ejercicio incluido
    with pytest.raises(catalog.CatalogError):
        catalog.delete_cifrado("03-pop-sol")
    catalog.delete_cifrado("mi-canción")
    assert "mi-canción" not in [c["id"] for c in catalog.cifrados()]


# ---------------------------------------------------------------- juicio de acordes rasgueados
def synth_strums(chart, wrong_bar=None, wrong_frets=None, lead=0.8, seed=1):
    """Toma rasgueada (Karplus-Strong): un rasguido por tiempo, con capo."""
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


@pytest.mark.parametrize("cid", [c["id"] for c in catalog.cifrados()])
def test_every_cifrado_played_right_has_no_errors(tmp_path, cid):
    r = run_chart(tmp_path, catalog.get_cifrado(cid))
    assert [i for i in r["issues"] if i["type"] != "timing"] == []


@pytest.mark.parametrize("cid,bar,wrong,grid_bar,label", [
    ("03-pop-sol", 3, "E", 3, "Em"),             # mayor en vez de menor
    ("05-vals", 3, "D", 3, "Dm"),                # D en vez de Dm, en 3/4
    ("09-cadd9", 2, "C", 2, "G"),                # acorde equivocado, con capo 2
    ("07-rock-quintas", 2, "A5", 2, "G5"),       # quinta equivocada
])
def test_wrong_chords_are_caught(tmp_path, cid, bar, wrong, grid_bar, label):
    r = run_chart(tmp_path, catalog.get_cifrado(cid), wrong_bar=bar, wrong_frets=catalog.get_chord(wrong)["frets"])
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


# ---------------------------------------------------------------- progreso
def test_streak_and_levels():
    assert progress.streak(["2026-01-01", "2026-01-02", "2026-01-03"], date(2026, 1, 3)) == 3
    assert progress.streak(["2026-01-01", "2026-01-02"], date(2026, 1, 3)) == 2    # hoy todavía no
    assert progress.streak(["2026-01-01"], date(2026, 1, 3)) == 0
    assert progress.level(0)["level"] == 1 and progress.level(150)["level"] == 2
    assert progress.level(99999)["next_xp"] is None


def _report(score, judged=4, events=4, first=4, fixed=0):
    return dict(summary=dict(score=score, judged=judged, events=events, first_try=first, fixed=fixed),
                reference=dict(name="x"))


def test_exercise_and_lesson_awards():
    lid = "em-am"
    exs = catalog.get_lesson(lid)["exercises"]
    out = progress.on_session(dict(type="exercise", lesson=lid, exercise=exs[0]["id"], min=75), _report(60))
    assert out["passed"] is False and out["xp"] == 0
    out = progress.on_session(dict(type="exercise", lesson=lid, exercise=exs[0]["id"], min=75), _report(90))
    assert out["passed"] and out["xp"] == progress.XP["exercise"]
    again = progress.on_session(dict(type="exercise", lesson=lid, exercise=exs[0]["id"], min=75), _report(95))
    assert again["xp"] == 0                         # aprobar de nuevo no vuelve a sumar
    for ex in exs[1:]:
        out = progress.on_session(dict(type="exercise", lesson=lid, exercise=ex["id"], min=ex["min"]), _report(100))
    assert out.get("lesson_done") and lid in progress.get()["lessons"]
    assert progress.get()["streak"] == 1 and progress.get()["practiced_today"]


def test_chord_and_drill_awards():
    out = progress.on_session(dict(type="chord", chord="Em"), _report(100, judged=1, events=1, first=1))
    assert out["passed"] and out["xp"] == progress.XP["chord"]
    assert progress.chord_mastered("Em", "camara")["xp"] == 0          # ya estaba dominado
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
    assert {g["id"] for g in c.get("/api/acordes").json()["groups"]} >= {"cejilla", "quintas"}
    assert len(c.get("/api/cifrados").json()) >= 10
    assert c.get("/api/cifrados/03-pop-sol").json()["chart"]["bpm"] == 90
    v = c.post("/api/cifrados/validar", json=dict(text="G | X9")).json()
    assert v["ok"] is False and "X9" in v["error"]
    saved = c.post("/api/cifrados", json=dict(text="titulo: Mía\nG | C\n")).json()
    assert c.post("/api/preview", json=dict(cifrado=saved["id"])).status_code == 200
    assert c.delete(f"/api/cifrados/{saved['id']}").json()["ok"]
    ruta = c.get("/api/ruta").json()
    assert ruta["next"]["id"] == "cuerdas"
    assert c.post("/api/progreso/tutoria", json=dict(lesson="cuerdas", url="javascript:alert(1)")).status_code == 400
    c.post("/api/progreso/tutoria", json=dict(lesson="cuerdas", url="https://www.youtube.com/watch?v=abcdefghijk"))
    assert c.get("/api/ruta").json()["levels"][0]["lessons"][0]["pinned"].endswith("abcdefghijk")
    assert c.post("/api/progreso/acorde", json=dict(chord="Em", via="camara")).json()["xp"] == progress.XP["chord"]
    assert c.post("/api/progreso/acorde", json=dict(chord="Zz", via="camara")).status_code == 400
    for path in ("/static/main.js", "/static/views/camara.js", "/static/vendor/tasks-vision/vision_bundle.mjs"):
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
    assert c.post("/api/live/start", json=dict(acorde="Em", simulate="r.wav", fast=True)).status_code == 200
    rep = _wait_report(c)
    assert rep["award"]["passed"] is ok
    assert ("Em" in c.get("/api/progreso").json()["chords"]) is ok


def test_lesson_exercise_over_api():
    c = TestClient(app)
    chart = catalog.chart_from_chord("Em", 4)
    _upload(c, _wav(dict(chart, bpm=60)), "em4.wav")
    r = c.post("/api/live/start", json=dict(ejercicio=dict(lesson="em", exercise="em4"), simulate="em4.wav", fast=True))
    assert r.status_code == 200 and r.json()["context"]["type"] == "exercise"
    rep = _wait_report(c)
    assert rep["award"]["passed"] and rep["award"]["lesson_done"]
    assert c.get("/api/ruta").json()["levels"][0]["lessons"][1]["done"]


def test_minuto_de_cambio_over_api():
    c = TestClient(app)
    chart = catalog.chart_alternating(["Em", "Am"], 5)            # 10 rasguidos limpios = 9 cambios
    _upload(c, _wav(dict(chart, bpm=90)), "cambios.wav")
    r = c.post("/api/live/start", json=dict(drill=dict(chords=["Em", "Am"], seconds=60), simulate="cambios.wav", fast=True))
    assert r.status_code == 200
    a = _wait_report(c)["award"]
    assert a["changes"] == 9 and a["record"] and a["xp"] == 4
    assert c.get("/api/progreso").json()["drills"]["Em-Am"] == 9
