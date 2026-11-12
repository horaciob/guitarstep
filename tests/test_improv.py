"""Improvising over a backing: notes heard against the chord and the scale, and the solo's report."""
import numpy as np
from fastapi.testclient import TestClient

from guitarr import improv
from guitarr.core import Grid
from guitarr.gui.server import app

G = Grid([i * 0.5 for i in range(200)])        # 120 bpm


def test_classify_against_the_chord_and_the_scale():
    assert improv.classify(57, "A7", "A", "minor_pentatonic") == "chord"       # A
    assert improv.classify(55, "A7", "A", "minor_pentatonic") == "chord"       # G, the 7th
    assert improv.classify(62, "A7", "A", "minor_pentatonic") == "scale"       # D
    assert improv.classify(58, "A7", "A", "minor_pentatonic") == "outside"     # Bb
    assert improv.classify(66, "E5", "E", "follow") == "scale"                 # F# over a power chord (dorian)
    assert improv.classify(59, "E5", "E", "follow") == "chord"                 # B, the fifth


def _notes(seq, step=0.25):
    return [dict(t=i * step, midi=m, cls=c, chord="A7") for i, (m, c) in enumerate(seq)]


def test_an_outside_note_that_steps_into_the_scale_is_an_approach():
    seq = [(57, "chord"), (60, "scale"), (61, "chord"), (62, "scale"), (63, "outside"), (64, "chord"),
           (67, "chord"), (69, "chord"), (72, "scale")]
    r = improv.report(_notes(seq, 0.4), G, 12)
    assert r["counts"]["approach"] == 1 and r["counts"]["outside"] == 0 and r["fits_pct"] == 100


def test_tips_for_a_busy_narrow_solo_off_the_chords():
    seq = [(65 if i % 4 == 0 else 60, "outside" if i % 4 == 0 else "scale") for i in range(32)]   # F (a leap to C), nonstop
    r = improv.report(_notes(seq, 0.25), G, 16)
    assert "outside" in r["tips"] and len(r["tips"]) == 2 and r["space_pct"] == 0
    assert r["score"] < 60


def test_a_good_solo_scores_high_and_has_no_tips():
    # phrases of chord tones on the beat with scale notes between, a rest after each phrase, an octave and more
    seq, t = [], 0.0
    for phrase in ([57, 60, 62, 64], [64, 67, 69, 72], [69, 67, 64, 62], [60, 57, 55, 57]):
        for k, m in enumerate(phrase):
            cls = "chord" if m % 12 in (9, 1, 4, 7) else "scale"
            seq.append(dict(t=t + 0.5 * k, midi=m, cls=cls, chord="A7"))
        t += 4.0                                    # 4 notes in 2 beats, then 6 beats of rest
    for x in seq:                                   # on the beat: make them chord tones
        if (x["t"] / 0.5) % 2 == 0:
            x["cls"] = "chord"
    r = improv.report(seq, G, 32)
    assert r["tips"] == [] and r["score"] >= 85


def test_too_few_notes():
    assert improv.report(_notes([(57, "chord")] * 3), G, 8) == dict(n=3, score=None, tips=["play_more"])


def test_api_backings_and_validation():
    c = TestClient(app)
    b = c.get("/api/improv/backings").json()
    assert b["blues_a"]["bars"][0] == "A7" and b["blues_a"]["scale"] == "blues"
    for bad, code in ((dict(backing="nope"), "bad_backing"), (dict(scale="nope"), "bad_scale"), (dict(key="H"), "bad_key")):
        assert c.post("/api/live/start", json=dict(improv=bad)).json()["detail"]["code"] == code


def test_live_improv_session_over_the_blues(tmp_path):
    """A simulated solo: A minor pentatonic notes with an outside Bb, heard against the 12-bar blues."""
    import soundfile as sf

    from guitarr.reference import RefOptions, load_reference
    from guitarr.session import LiveOptions, LiveSession

    sr = 22050
    notes = [57, 60, 62, 64, 67, 58, 69, 67, 64, 62, 60, 57] * 2
    out = [np.zeros(int(sr * 0.3))]
    for m in notes:
        n = int(sr * 0.33)
        f = 440 * 2 ** ((m - 69) / 12)
        t = np.arange(n) / sr
        out += [0.3 * sum(np.sin(2 * np.pi * h * f * t) / h for h in range(1, 5)) * np.exp(-t / 0.4), np.zeros(int(sr * 0.0))]
    wav = tmp_path / "solo.wav"
    sf.write(wav, np.concatenate(out).astype(np.float32), sr)
    ref = load_reference(RefOptions(chart=improv.chart("blues_a", 90, 1)), log=lambda m: None)
    r = LiveSession(ref, LiveOptions(mode="improv", simulate=wav, fast=True, improv_key="A", improv_scale="minor_pentatonic")).run()
    s = r["summary"]
    assert r["mode"] == "improv" and s["n"] >= 20
    heard = [n["midi"] for n in r["notes"]]
    assert heard.count(58) >= 1 and all(n["cls"] == "outside" for n in r["notes"] if n["midi"] == 58)
    assert all(n["chord"] == "A7" for n in r["notes"][:8])                    # the first bars are A7
    assert s["fits_pct"] >= 85 and s["score"] is not None


def test_neck_game_targets_follow_the_strings_and_the_tuning():
    from guitarr import config
    from guitarr.gui.server import ref_options

    opts, ctx = ref_options(dict(neck=dict(strings=[6, 5], seconds=30)))
    steps = opts.tab
    assert ctx == dict(type="neck", mode="wait", seconds=30, key="56-30")
    assert len(steps) == 150 and {s["string"] for s in steps} == {5, 6}
    assert all(s["pitch"] % 12 in (0, 2, 4, 5, 7, 9, 11) and 0 <= s["fret"] < 12 for s in steps)
    assert all((a["string"], a["pitch"]) != (b["string"], b["pitch"]) for a, b in zip(steps, steps[1:]))
    config.save_instrument(tuning="drop_d")
    opts, ctx = ref_options(dict(neck=dict(strings=[6], accidentals=True)))
    assert ctx["key"] == "6#-60"
    assert all(s["pitch"] == 38 + s["fret"] for s in opts.tab)               # the low string is a D


def test_neck_game_keeps_the_best():
    from guitarr import progress

    rep = dict(summary=dict(first_try=12, fixed=2))
    a = progress.on_session(dict(type="neck", seconds=60, key="56-60"), rep)
    assert a["found"] == 14 and a["xp"] == 5 and a["record"] is False
    a = progress.on_session(dict(type="neck", seconds=60, key="56-60"), dict(summary=dict(first_try=5, fixed=0)))
    assert a["best"] == 14 and progress.get()["neck"]["56-60"]["last"] == 5
