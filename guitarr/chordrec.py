"""A chord chart from a recording: finds the beat, hears the chord on each beat and writes it as a chart.

Chroma (12 pitch classes) is taken from the harmonic part of the sound and averaged per beat; each beat is matched
against major, minor and dominant-7th chord shapes; a smoothing pass keeps the chord from flickering (a change
costs something, so it only changes when the music does). Beats are grouped in bars of 4 (or `beats_per_bar`),
one chord per bar or two when it changes in the middle. It's a first draft to fix by ear, not a transcription."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import catalog

ROOTS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
SHAPES = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10]}
CHANGE_COST = 0.12          # how much better a new chord must fit to change on this beat
MIN_ENERGY = 0.08           # quieter beats (relative to the loudest) are silence: no chord


def templates() -> tuple[list[str], np.ndarray]:
    names, rows = [], []
    for r, root in enumerate(ROOTS):
        for suf, ivs in SHAPES.items():
            v = np.zeros(12)
            for k, iv in enumerate(ivs):
                v[(r + iv) % 12] = 1.0 if k < 3 else 0.6     # the 7th weighs less than the triad
            names.append(root + suf)
            rows.append(v / np.linalg.norm(v))
    return names, np.array(rows)


def beat_chords(chroma: np.ndarray, energy: np.ndarray) -> list[str | None]:
    """chroma: 12 × beats. The best chord per beat, smoothed with a cost for changing."""
    names, T = templates()
    c = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)
    fit = T @ c                                               # chords × beats, cosine
    n, b = fit.shape
    score, back = fit[:, 0].copy(), np.zeros((n, b), int)
    for j in range(1, b):                                     # Viterbi: stay, or change paying CHANGE_COST
        best = int(np.argmax(score))
        stay, move = score, score[best] - CHANGE_COST
        back[:, j] = np.where(stay >= move, np.arange(n), best)
        score = np.maximum(stay, move) + fit[:, j]
    path = [int(np.argmax(score))]
    for j in range(b - 1, 0, -1):
        path.append(back[path[-1], j])
    path.reverse()
    loud = energy / (energy.max() + 1e-9)
    return [names[k] if loud[j] >= MIN_ENERGY else None for j, k in enumerate(path)]


def downbeat(chords: list[str | None], bpb: int = 4) -> int:
    """Which beat starts the bars: the phase where the chord changes fall on the "one" most often."""
    changes = [j for j in range(1, len(chords)) if chords[j] != chords[j - 1]]
    return max(range(bpb), key=lambda o: (sum((j - o) % bpb == 0 for j in changes), -o))


def bars_of(chords: list[str | None], bpb: int = 4) -> list[list[str | None]]:
    """One chord per bar, or two halves when it changes in the middle (the chord heard most in each half)."""
    out = []
    for i in range(0, len(chords), bpb):
        bar = chords[i:i + bpb]
        if len(bar) < bpb // 2:
            break
        top = max(set(bar), key=bar.count)
        if bar.count(top) >= len(bar) - 1 or len(bar) < bpb:
            out.append([top])
        else:
            h = bpb // 2
            a, b2 = bar[:h], bar[h:]
            ca, cb = max(set(a), key=a.count), max(set(b2), key=b2.count)
            out.append([ca] if ca == cb else [ca, cb])
    return out


def chart_text(bars: list[list[str | None]], bpm: float, title: str, bpb: int = 4) -> str:
    names = {c for bar in bars for c in bar if c}
    unknown = [c for c in names if catalog.get_chord(c) is None]
    head = [f"title: {title}", f"bpm: {round(bpm)}", f"time: {bpb}/4"]
    if unknown:                                            # chords the dictionary can't finger: voice them
        head.append("voicing: triad")
    head.append("note: Made from a recording: a first draft. Check each chord by ear.")
    cells = [" ".join(c or "-" for c in bar) for bar in bars]
    lines = [" | ".join(cells[i:i + 4]) for i in range(0, len(cells), 4)]
    return "\n".join(head + ["", "[Song]"] + lines) + "\n"


def from_audio(path: Path, title: str | None = None, bpb: int = 4, max_seconds: float = 600) -> dict:
    import librosa

    y, sr = librosa.load(str(path), sr=22050, mono=True, duration=max_seconds)
    if len(y) < sr:
        raise ValueError("The recording is too short.")
    harm = librosa.effects.harmonic(y)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    tempo = float(np.atleast_1d(tempo)[0])
    if len(beats) < 2 * bpb:
        raise ValueError("Couldn't find a steady beat in the recording.")
    period = int(np.median(np.diff(beats)))
    lead = np.arange(beats[0] - period, period // 2, -period)[::-1]          # the tracker often starts late: the
    beats = np.concatenate([lead, beats]).astype(int)                         # beats before it, at the same tempo
    chroma = librosa.feature.chroma_cqt(y=harm, sr=sr)
    tail = np.arange(beats[-1] + period, chroma.shape[1], period)            # and after it, to the end
    beats = np.concatenate([beats, tail]).astype(int)
    sync = librosa.util.sync(chroma, beats, aggregate=np.median)[:, :-1]      # between beats
    rms = librosa.feature.rms(y=y)[0]
    energy = librosa.util.sync(rms[None, :], beats, aggregate=np.mean)[0, :-1]
    chords = beat_chords(sync, energy)
    while chords and chords[0] is None:                                       # silence before the music
        chords.pop(0)
    chords = chords[downbeat(chords, bpb):]
    bars = bars_of(chords, bpb)
    text = chart_text(bars, tempo, title or Path(path).stem, bpb)
    return dict(text=text, bpm=round(tempo), bars=len(bars), chords=sorted({c for b in bars for c in b if c}))
