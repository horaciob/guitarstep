"""Live mode with --simulate (no guitar) + individual follower pieces."""
import numpy as np
import pytest

from guitarr.core import Grid, Note
from guitarr.dsp import Detection, Detector, Recorder, chroma
from guitarr.follow import Event, Judge, TempoFollower, Trainer, describe, group_events
from guitarr.reference import RefOptions, load_reference
from guitarr.session import LiveOptions, LiveSession

SR = 44100


def run_sim(demo_dir, **kw):
    ref = load_reference(RefOptions(demo_dir / "reference.mid"), log=lambda m: None)
    opts = LiveOptions(simulate=demo_dir / "take.wav", fast=True, **kw)
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
    assert s["extras"] <= 1                    # the planted extra note (and no false ones)
    assert len(r["passes"]) == 1
    assert {"bar", "notes", "errors", "timing"} <= set(r["bars"][0])


def test_wait_mode_simulated(demo_dir):
    r = run_sim(demo_dir, mode="wait")
    i = issues(r)
    assert ("missed", 1, 3.5) in i             # E4 skipped (F4 was played)
    assert ("missed", 2, 3.0) in i             # G4 never sounded
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
    ev = Event(0.0, [45, 52, 57, 61])            # A major: A E A C#
    judge = Judge()
    hear = lambda ps: Detection(0.0, None, 0.0, chroma(sum(tone(p) for p in ps), SR), -20.0)
    res, detail = judge(ev, hear([45, 52, 57, 61]))
    assert res == "ok"
    res, detail = judge(ev, hear([45, 52, 57, 60]))   # A minor instead of A major
    assert res == "wrong" and detail["kind"] == "chord_wrong"
    assert dict(note="C#", interval="maj3") in detail["missing"] and "C" in detail["extra"]
    assert describe(detail).startswith("chord: missing C# (major 3rd), extra C")
    res, detail = judge(ev, hear([45, 52, 57]))       # no third: passes, but says so
    assert res == "ok" and detail["unheard"] == ["C#"]
    res, detail = Judge(transpose=2)(ev, hear([43, 50, 55, 59]))  # tuned a whole step down
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
    assert n_clicks == 4 + 4                      # count-in + one bar
    for e in f.events:
        f.on_detection(fake_det(e.due + 0.01, e.pitches[0]))
    msg = f.tick(f.pass_end + 0.01)
    assert f.passes[0]["score"] == 100
    assert f.speed == pytest.approx(0.6)
    assert msg["code"] == "pass" and msg["params"]["new_speed"] == 0.6 and "50% → 60%" in msg["text"]
    assert len(f.clicks) > n_clicks               # scheduled the next pass
    assert all(e.status == "pending" for e in f.events)
    # one bad pass keeps the tempo you earned; a second one in a row slows down
    f.tick(f.pass_end + 0.01)
    assert f.passes[-1]["score"] == 0 and f.speed == pytest.approx(0.6)
    f.tick(f.pass_end + 0.01)
    assert f.passes[-1]["score"] == 0 and f.speed == pytest.approx(0.5)


def test_position_follows_the_metronome_in_beats():
    notes = [Note(k * 0.5, k * 0.5 + 0.4, 60 + k) for k in range(4)]
    grid = Grid(np.arange(12) * 0.5, 4)
    f = TempoFollower(group_events(notes), Judge(), speed=0.5, window=0.2, grid=grid, click=True)
    assert f.position(0.0) is None                # not scheduled yet
    f.schedule(1.0)                               # count-in: 4 beats of 1 s (0.5 s at 50%)
    assert f.position(1.0) == pytest.approx(-4)
    assert f.position(5.0) == pytest.approx(0)    # first beat of the section
    assert f.position(7.5) == pytest.approx(2.5)


def test_note_late_inside_window_is_not_marked_missed_before_analysis(demo_dir):
    """The follower must not close a note's window while its onset is still being
    analyzed (~110 ms of lag)."""
    notes = [Note(0.0, 0.4, 60), Note(1.0, 1.4, 62)]
    grid = Grid(np.arange(8) * 0.5, 4)
    f = TempoFollower(group_events(notes), Judge(), speed=1.0, window=0.2, grid=grid, click=False)
    f.start(1.0)
    ev = f.events[1]
    f.tick(ev.due + ev.win - 0.01)  # the analysis horizon hasn't passed the window yet
    assert ev.status == "pending"
    f.on_detection(fake_det(ev.due + 0.15, 62))
    assert ev.status == "ok"


# ---------------------------------------------------------------- bends and licks
def synth_curve(tries, gap=0.4, lead=0.3):
    """Picked notes whose pitch follows keyframes [(seconds, midi), ...], one list per note."""
    out = [np.zeros(int(SR * lead))]
    for keys in tries:
        ts, ms = zip(*keys)
        n = int(SR * ts[-1])
        m = np.interp(np.arange(n) / SR, ts, ms)
        ph = 2 * np.pi * np.cumsum(440 * 2 ** ((m - 69) / 12)) / SR
        y = sum(np.sin(h * ph) / h for h in range(1, 6))
        env = (np.minimum(1, np.arange(n) / (0.003 * SR)) * np.exp(-np.arange(n) / (2.5 * SR))
               * np.minimum(1, (n - np.arange(n)) / (0.03 * SR)))
        out += [0.3 * y * env, np.zeros(int(SR * gap))]
    return np.concatenate(out).astype(np.float32)


def run_wav(tmp_path, y, ref, **kw):
    import soundfile as sf

    wav = tmp_path / "take.wav"
    sf.write(wav, y, SR)
    return LiveSession(ref, LiveOptions(simulate=wav, fast=True, **kw)).run()


def test_bend_tries_are_judged_by_the_held_pitch(tmp_path):
    from guitarr import catalog

    ref = load_reference(RefOptions(tab=catalog.bend_steps(dict(string=3, fret=7, bend=2, tries=4))), log=lambda m: None)
    assert [n.pitch for n in ref.notes] == [64] * 4 and ref.notes[0].glide_from == 62
    y = synth_curve([
        [(0, 62), (0.3, 62), (0.45, 64), (1.8, 64), (1.9, 62), (2.2, 62)],   # in tune, held: hit
        [(0, 62), (1.0, 62)],                                                # picked, no bend: not a try
        [(0, 62), (0.3, 62), (0.45, 63.4), (1.8, 63.4)],                     # 60 cents flat
        [(0, 62), (0.3, 62), (0.45, 64), (0.9, 64), (1.0, 62), (1.4, 62)],   # let go after 0.5 s
        [(0, 62), (0.2, 62), (0.35, 64.6), (1.8, 64.6)],                     # 60 cents sharp
    ])
    r = run_wav(tmp_path, y, ref, mode="bend", hold=1.0)
    kinds = [it["detail"]["kind"] for it in r["issues"]]
    assert kinds == ["bend_flat", "bend_short", "bend_sharp"]
    assert r["summary"]["judged"] == r["summary"]["events"] == 4
    assert r["summary"]["score"] == 25
    flat, short, sharp = (it["detail"] for it in r["issues"])
    assert -75 < flat["cents"] < -45 and 0.3 <= short["held"] <= 0.7 and 45 < sharp["cents"] < 75
    assert "fell short" in describe(flat) and "too far" in describe(sharp)


def test_lick_bend_and_slide_dont_count_the_notes_on_the_way(tmp_path):
    from guitarr import catalog

    ref = load_reference(RefOptions(tab=catalog.parse_lick("3:7b9 3:5/7 2:5")), log=lambda m: None)
    assert [(n.pitch, n.fret, n.glide_from) for n in ref.notes] == [(64, 7, 62), (60, 5, None), (62, 7, 60), (64, 5, None)]
    y = synth_curve([
        [(0, 62), (0.25, 62), (0.45, 64), (0.8, 64)],     # pick D, bend slowly to E
        [(0, 60), (0.35, 60), (0.40, 62), (0.8, 62)],     # C, quick slide to D
        [(0, 64), (0.5, 64)],
    ], gap=0.15)
    r = run_wav(tmp_path, y, ref, mode="wait")
    assert r["summary"]["first_try"] == 4 and r["issues"] == []


def synth_together(groups, dur=0.7, gap=0.25, lead=0.3):
    """Picked moments, each a list of midi notes sounding at once (a pinch or a double stop)."""
    out = [np.zeros(int(SR * lead))]
    n = int(SR * dur)
    tt = np.arange(n) / SR
    env = np.minimum(1, tt / 0.003) * np.exp(-tt / 1.5) * np.minimum(1, (n - np.arange(n)) / (0.03 * SR))
    for g in groups:
        y = sum(np.sin(2 * np.pi * h * 440 * 2 ** ((m - 69) / 12) * tt) / h for m in g for h in range(1, 6))
        out += [0.25 * y * env / len(g), np.zeros(int(SR * gap))]
    return np.concatenate(out).astype(np.float32)


def test_notes_played_together_are_heard_together(tmp_path):
    from guitarr import catalog

    steps = catalog.parse_lick("6:3 5:3+1:0 4:2 3:7+2:8~")
    assert [s.get("together", False) for s in steps] == [False, False, True, False, False, True]
    ref = load_reference(RefOptions(tab=steps), log=lambda m: None)
    assert [n.start for n in ref.notes] == [0, 1, 1, 2, 3, 3]          # together: the same beat
    assert len(group_events(ref.notes)) == 4
    # G2 · pinch C3+E4 (bass and melody) · E3 · double stop D4+G4
    good = synth_together([[43], [48, 64], [52], [62, 67]])
    r = run_wav(tmp_path, good, ref, mode="wait")
    assert r["summary"]["first_try"] == 4 and r["issues"] == []
    # the thumb plays its bass but the finger doesn't pinch the melody: not passed on the first try
    bad = synth_together([[43], [48], [52], [62, 67]])
    r = run_wav(tmp_path, bad, ref, mode="wait")
    assert r["summary"]["first_try"] < 4


def test_notes_together_must_be_plain_and_on_different_strings():
    from guitarr import catalog

    for tab in ("3:5h7+2:5", "3:5+3:7", "3:5+"):
        with pytest.raises(catalog.CatalogError):
            catalog.parse_lick(tab)
    shifted = catalog.parse_lick("6:3+1:3", shift=-5)                    # falls off the neck: an octave up
    assert [s["fret"] for s in shifted] == [10, 10]
