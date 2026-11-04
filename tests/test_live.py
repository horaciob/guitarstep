"""Modo en vivo con --simulate (sin guitarra) + piezas sueltas del seguidor."""
import numpy as np
import pytest

from guitarr.core import Grid, Note
from guitarr.dsp import Detection, Detector, Recorder, chroma
from guitarr.follow import Event, Judge, TempoFollower, Trainer, group_events
from guitarr.reference import RefOptions, load_reference
from guitarr.session import LiveOptions, LiveSession

SR = 44100


def run_sim(demo_dir, **kw):
    ref = load_reference(RefOptions(demo_dir / "referencia.mid"), log=lambda m: None)
    opts = LiveOptions(simulate=demo_dir / "toma.wav", fast=True, **kw)
    return LiveSession(ref, opts).run()


def issues(r):
    return {(it["type"], it["bar"], round(it["beat"], 1)) for it in r["issues"]}


def test_tempo_mode_simulated(demo_dir):
    r = run_sim(demo_dir, mode="tempo", speed=0.9)
    s = r["summary"]
    assert s["judged"] == s["events"] == 33
    i = issues(r)
    assert ("wrong", 1, 3.5) in i
    assert ("missed", 2, 3.0) in i
    assert ("timing", 4, 2.0) in i
    assert s["extras"] <= 1                    # la nota de más plantada (y ninguna falsa)
    assert len(r["passes"]) == 1
    assert {"bar", "notes", "errors", "timing"} <= set(r["bars"][0])


def test_wait_mode_simulated(demo_dir):
    r = run_sim(demo_dir, mode="wait")
    i = issues(r)
    assert ("missed", 1, 3.5) in i             # E4 salteada (tocó F4)
    assert ("missed", 2, 3.0) in i             # G4 nunca sonó
    assert r["summary"]["first_try"] >= 29


def synth_legato(pitches, dur=0.35, lead=0.3, glide=0.02):
    f = np.concatenate([np.full(int(SR * dur), 440 * 2 ** ((p - 69) / 12)) for p in pitches])
    k = int(glide * SR)
    f = np.convolve(np.pad(f, (k, k), mode="edge"), np.ones(k) / k, "same")[k:-k]
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = sum(np.sin(h * ph) / h for h in range(1, 6))
    n = len(y)
    env = (np.minimum(1, np.arange(n) / (0.003 * SR)) * np.exp(-np.arange(n) / (1.5 * SR))
           * np.minimum(1, (n - np.arange(n)) / (0.05 * SR)))
    return np.concatenate([np.zeros(int(SR * lead)), 0.3 * y * env, np.zeros(int(SR * 0.3))]).astype(np.float32)


def detect(y, **kw):
    rec = Recorder(SR)
    det = Detector(rec, **kw)
    out = []
    for i in range(0, len(y), 256):
        rec.append(y[i:i + 256])
        out += det.process()
    return out


def test_legato_onsets_are_recovered():
    y = synth_legato([57, 59, 60, 59])           # A3 hammer B3 hammer C4 pull B3
    without = detect(y, sensitivity=0.25, legato=False)
    with_leg = detect(y, sensitivity=0.25, legato=True)
    assert len(without) < 4
    assert [round(d.midi) for d in with_leg] == [57, 59, 60, 59]
    assert any(d.legato for d in with_leg)
    for d, t in zip(with_leg, [0.3, 0.65, 1.0, 1.35]):
        assert abs(d.t - t) < 0.05


def test_chord_feedback_names_missing_note():
    t = np.arange(4096) / SR
    tone = lambda m: sum(np.sin(2 * np.pi * h * 440 * 2 ** ((m - 69) / 12) * t) / h for h in range(1, 4))
    ev = Event(0.0, [45, 52, 57, 61])            # La mayor: A E A C#
    judge = Judge()
    hear = lambda ps: Detection(0.0, None, 0.0, chroma(sum(tone(p) for p in ps), SR), -20.0)
    res, detail = judge(ev, hear([45, 52, 57, 61]))
    assert res == "ok"
    res, detail = judge(ev, hear([45, 52, 57, 60]))   # La menor en vez de La mayor
    assert res == "wrong"
    assert "faltó C# (3ra)" in detail and "sobró C" in detail
    res, detail = judge(ev, hear([45, 52, 57]))       # sin la 3ra: pasa, pero avisa
    assert res == "ok" and "no se escuchó C#" in detail
    res, detail = Judge(transpose=2)(ev, hear([43, 50, 55, 59]))  # afinado un tono abajo
    assert res == "ok"


def fake_det(t, midi):
    return Detection(t, float(midi), 0.95, np.zeros(12), -20.0)


def test_trainer_speeds_up_after_clean_pass_and_loops():
    notes = [Note(k * 0.5, k * 0.5 + 0.4, 60 + k) for k in range(4)]
    grid = Grid(np.arange(12) * 0.5, 4)
    f = TempoFollower(group_events(notes), Judge(), speed=0.5, window=0.2, grid=grid,
                      trainer=Trainer(step=0.1, target=90, max_speed=1.0), click=True)
    f.schedule(1.0)
    n_clicks = len(f.clicks)
    assert n_clicks == 4 + 4                      # cuenta de entrada + un compás
    for e in f.events:
        f.on_detection(fake_det(e.due + 0.01, e.pitches[0]))
    msg = f.tick(f.pass_end + 0.01)
    assert f.passes[0]["score"] == 100
    assert f.speed == pytest.approx(0.6)
    assert "50% → 60%" in msg
    assert len(f.clicks) > n_clicks               # programó la vuelta siguiente
    assert all(e.status == "pending" for e in f.events)
    # vuelta mala: baja
    f.tick(f.pass_end + 0.01)
    assert f.passes[-1]["score"] == 0 and f.speed == pytest.approx(0.5)


def test_note_late_inside_window_is_not_marked_missed_before_analysis(demo_dir):
    """El seguidor no debe cerrar la ventana de una nota mientras su ataque todavía
    se está analizando (~110 ms de retardo)."""
    notes = [Note(0.0, 0.4, 60), Note(1.0, 1.4, 62)]
    grid = Grid(np.arange(8) * 0.5, 4)
    f = TempoFollower(group_events(notes), Judge(), speed=1.0, window=0.2, grid=grid, click=False)
    f.start(1.0)
    ev = f.events[1]
    f.tick(ev.due + ev.win - 0.01)  # el horizonte de análisis todavía no pasó la ventana
    assert ev.status == "pending"
    f.on_detection(fake_det(ev.due + 0.15, 62))
    assert ev.status == "ok"
