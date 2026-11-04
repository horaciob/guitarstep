"""File mode against the demo (known planted mistakes, see guitarr/demo.py)."""
import numpy as np

from guitarr import analysis
from guitarr.analysis import FileOptions, align, compare, initial_shift, onset_tolerances
from guitarr.core import Note
from guitarr.reference import RefOptions, load_reference, transcribe


def _types(result):
    return {(it["type"], it["bar"], round(it["beat"], 1)) for it in result["issues"]}


def test_demo_file_mode_finds_planted_errors(demo_dir):
    ref = load_reference(RefOptions(demo_dir / "reference.mid"), log=lambda m: None)
    res, _ = analysis.analyze_take(ref, demo_dir / "take.wav", FileOptions(), log=lambda m: None)
    s = res["summary"]
    assert round(100 * s["tempo_ratio"]) == 90          # played at 90 vs 100 bpm
    t = _types(res)
    assert ("wrong", 1, 3.5) in t                         # note 6: F4 instead of E4
    assert ("missing", 2, 3.0) in t                       # note 13 missing
    assert ("extra", 3, 3.2) in t                         # extra note (C5)
    assert ("timing", 4, 2.0) in t                        # note 27, late
    late = next(it for it in res["issues"] if it["type"] == "timing")
    assert 80 <= late["dt_ms"] <= 140
    assert s["wrong"] == 1 and s["missing"] == 1
    assert {b["bar"] for b in res["bars"]} == {1, 2, 3, 4, 5}


def test_noise_before_playing_doesnt_break_alignment(demo_dir):
    ref = load_reference(RefOptions(demo_dir / "reference.mid"), log=lambda m: None)
    usr = transcribe(demo_dir / "take.wav")
    noisy = [Note(0.15, 0.4, 40, 0.9)] + usr                # a hit on the open 6th string before starting
    res = compare(ref, noisy, FileOptions(), log=lambda m: None)
    t = _types(res)
    assert ("wrong", 1, 3.5) in t and ("missing", 2, 3.0) in t and ("timing", 4, 2.0) in t
    assert res["summary"]["correct"] >= 30


def test_initial_shift_skips_leading_noise():
    ref = [Note(0, 0.3, 57), Note(0.3, 0.6, 60), Note(0.6, 0.9, 62)]
    usr = [Note(0.2, 0.4, 40), Note(1.0, 1.3, 57), Note(1.3, 1.6, 60)]
    assert initial_shift(ref, usr) == 1.0


def _align_slow(ref, usr, smooth_s):
    import librosa

    FPS = analysis.FPS
    end = max(max(n.end for n in ref), max(n.end for n in usr))
    Cr, Cu = analysis.note_chroma(ref, end), analysis.note_chroma(usr, end)
    _, wp = librosa.sequence.dtw(X=Cr, Y=Cu, metric="cosine")
    wp = wp[::-1]
    u_idx = np.arange(Cu.shape[1])
    r = np.array([wp[wp[:, 1] == u, 0].mean() if np.any(wp[:, 1] == u) else np.nan for u in u_idx])
    ok = ~np.isnan(r)
    r = np.interp(u_idx, u_idx[ok], r[ok])
    w = max(1, int(smooth_s * FPS)) | 1
    pad = np.pad(r, w // 2, mode="reflect", reflect_type="odd")
    r = np.convolve(pad, np.ones(w) / w, mode="valid")
    return np.stack([u_idx / FPS, r / FPS])


def test_align_matches_original():
    rng = np.random.default_rng(3)
    ref = [Note(k * 0.3, k * 0.3 + 0.25, int(rng.integers(50, 70))) for k in range(60)]
    usr = [Note(n.start * 1.1 + 0.4, n.end * 1.1 + 0.4, n.pitch) for n in ref]
    np.testing.assert_allclose(align(ref, usr, 2.0), _align_slow(ref, usr, 2.0))


def test_onset_tolerance_shrinks_in_fast_passages():
    fast = [Note(k * 0.1, k * 0.1 + 0.08, 60) for k in range(10)]   # fusas a 150 bpm
    slow = [Note(k * 0.5, k * 0.5 + 0.4, 60) for k in range(4)]
    assert np.all(onset_tolerances(fast, 0.15) <= 0.061)
    assert np.all(onset_tolerances(slow, 0.15) == 0.15)


def test_section_analysis_ignores_notes_outside_the_section(demo_dir):
    ref = load_reference(RefOptions(demo_dir / "reference.mid", start_bar=1, end_bar=2), log=lambda m: None)
    res, _ = analysis.analyze_take(ref, demo_dir / "take.wav", FileOptions(), log=lambda m: None)
    assert {it["bar"] for it in res["issues"]} <= {1, 2}
    assert res["summary"]["extra"] == 0
