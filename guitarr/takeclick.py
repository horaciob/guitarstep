"""The metronome of a take, for listening back: the clicks you heard, saved next to the take.

The take itself (take-….wav) stays the clean guitar, because analysis grades it. Beside it,
take-….click.json keeps the clicks on the recording's own clock (shifted by the input latency, so
they line up with what you played) and the tempo. Listening "with the metronome" mixes them in on
the fly.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np

SUFFIX = ".click.json"


def click_path(take: Path) -> Path:
    return take.with_suffix(SUFFIX)


def click_waves(sr: int, volume: float = 1.0) -> dict[bool, np.ndarray]:
    """The metronome's two clicks: accented (beat 1) and plain."""
    n = int(0.03 * sr)
    env = np.exp(-np.arange(n) / (0.006 * sr))
    tt = np.arange(n) / sr
    return {True: (0.6 * volume * env * np.sin(2 * np.pi * 1600 * tt)).astype(np.float32),
            False: (0.4 * volume * env * np.sin(2 * np.pi * 1000 * tt)).astype(np.float32)}


LOOP_TONES = (600.0, 900.0, 1350.0, 2025.0)   # Hz: the cable test cycles these, so each click can be recognized


def tone_waves(sr: int, tones: dict, volume: float = 1.0) -> dict:
    """A click per key, each at its own frequency ({key: Hz} -> {key: wave})."""
    n = int(0.03 * sr)
    env = np.exp(-np.arange(n) / (0.008 * sr))
    tt = np.arange(n) / sr
    return {k: (0.5 * volume * env * np.sin(2 * np.pi * f * tt)).astype(np.float32) for k, f in tones.items()}


def save(take: Path, clicks: list[tuple[float, bool]], bpm: float | None, final_bpm: float | None = None) -> Path | None:
    if not clicks:
        return None
    p = click_path(take)
    p.write_text(json.dumps(dict(bpm=bpm, final_bpm=final_bpm,
                                 clicks=[[round(float(t), 4), bool(a)] for t, a in clicks])), encoding="utf-8")
    return p


def load(take: Path) -> dict | None:
    p = click_path(take)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if d.get("clicks") else None
    except (OSError, ValueError):
        return None


def info(take: Path) -> dict:
    """{click, bpm, final_bpm} for the UI."""
    d = load(take) or {}
    return dict(click=bool(d), bpm=d.get("bpm"), final_bpm=d.get("final_bpm"))


def mix(audio: np.ndarray, sr: int, clicks: list, guitar_peak: float | None = None) -> np.ndarray:
    """The take with its clicks, at a level that follows the guitar (audible, never covering it)."""
    out = np.asarray(audio, np.float32).copy()
    if out.ndim > 1:
        out = out.mean(axis=1)
    peak = guitar_peak if guitar_peak is not None else float(np.max(np.abs(out))) if len(out) else 0.0
    gain = min(1.0, max(0.12, 0.7 * peak) / 0.6)              # the accented click peaks at 0.6
    waves = click_waves(sr, gain)
    for t, accent in clicks:
        w = waves[bool(accent)]
        a = int(round(t * sr))
        if a >= len(out) or a + len(w) <= 0:
            continue
        lo, hi = max(0, a), min(len(out), a + len(w))
        out[lo:hi] += w[lo - a:hi - a]
    top = float(np.max(np.abs(out))) if len(out) else 0.0
    if top > 0.99:
        out *= 0.99 / top
    return out


def mixed_wav(take: Path) -> bytes | None:
    import soundfile as sf

    d = load(take)
    if not d:
        return None
    audio, sr = sf.read(take, dtype="float32")
    buf = io.BytesIO()
    sf.write(buf, mix(audio, sr, d["clicks"]), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()
