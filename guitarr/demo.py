"""Generates test files: a reference (MIDI + WAV) and a "take" with known mistakes.

The guitar is synthesized with Karplus-Strong (plucked string), which sounds much
more like a guitar than a sine wave and gives basic-pitch something realistic.

Mistakes planted in the take (to check that the detector finds them):
  - played slower (90 vs 100 bpm)
  - note 6:  one semitone up (wrong note)
  - note 13: not played (missing)
  - after note 21: one extra note
  - note 27: 120 ms late
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

SR = 44100

# A minor pentatonic lick: (MIDI pitch), eighth notes, 4 bars of 4/4
RIFF = [57, 60, 62, 64, 67, 64, 62, 60,
        57, 60, 62, 64, 67, 69, 67, 64,
        69, 67, 64, 62, 64, 62, 60, 57,
        55, 57, 60, 57, 55, 52, 55, 57]


def pluck(freq: float, dur: float, rng: np.random.Generator, decay: float = 0.996) -> np.ndarray:
    n = int(SR * dur)
    period = max(2, int(round(SR / freq - 0.5)))  # the averaging filter adds half a sample
    buf = rng.uniform(-1, 1, period)
    # Karplus-Strong as an IIR filter: y[n] = x[n] + d/2·(y[n-P] + y[n-P+1])
    from scipy.signal import lfilter

    x = np.zeros(n)
    x[:min(period, n)] = buf[:n]
    if n >= period:  # the recurrence already touches y[0] at n = P-1; compensate
        x[period - 1] -= 0.5 * decay * buf[0]
    a = np.zeros(period + 1)
    a[0], a[period - 1], a[period] = 1.0, -0.5 * decay, -0.5 * decay
    out = lfilter([1.0], a, x)
    fade = np.minimum(1, np.linspace(1, 0, n) * 20)  # fade out at the end
    return out * fade


def render(notes, total: float, rng) -> np.ndarray:
    y = np.zeros(int(SR * (total + 1.5)))
    for start, end, pitch in notes:
        s = pluck(pretty_midi.note_number_to_hz(pitch), end - start + 0.15, rng)
        a = int(start * SR)
        y[a:a + len(s)] += s * 0.4
    y += rng.normal(0, 0.003, len(y))  # a little background noise
    return (y / np.max(np.abs(y)) * 0.9).astype(np.float32)


def sequence(bpm: float, pitches, lead_in: float = 0.5, jitter: float = 0.0, rng=None):
    eighth = 60 / bpm / 2
    notes = []
    for k, p in enumerate(pitches):
        t = lead_in + k * eighth + (rng.normal(0, jitter) if jitter else 0)
        notes.append([t, t + eighth * 0.9, p])
    # final one-bar power chord (A2 E3 A3)
    t = lead_in + len(pitches) * eighth
    for p in (45, 52, 57):
        notes.append([t, t + 8 * eighth, p])
    return notes


def main(out: Path | str = "demo") -> Path:
    OUT = Path(out)
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)

    # ---- reference, 100 bpm
    ref = sequence(100, RIFF, lead_in=0.0)
    pm = pretty_midi.PrettyMIDI(initial_tempo=100)
    pm.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0))
    inst = pretty_midi.Instrument(program=25)
    inst.notes = [pretty_midi.Note(100, p, s, e) for s, e, p in ref]
    pm.instruments.append(inst)
    pm.write(str(OUT / "reference.mid"))
    sf.write(OUT / "reference.wav", render(ref, ref[-1][1], rng), SR)

    # ---- take with mistakes, 90 bpm, 1.2 s of leading silence, small inaccuracies
    take = sequence(90, RIFF, lead_in=1.2, jitter=0.012, rng=rng)
    eighth = 60 / 90 / 2
    take[5][2] += 1                       # note 6 wrong
    take[26][0] += 0.12                   # note 27 late
    take[26][1] += 0.12
    extra_t = take[20][0] + eighth * 0.5  # extra note between 21 and 22
    take.append([extra_t, extra_t + eighth * 0.4, 72])
    del take[12]                          # note 13 missing
    sf.write(OUT / "take.wav", render(sorted(take), max(n[1] for n in take), rng), SR)

    return OUT

