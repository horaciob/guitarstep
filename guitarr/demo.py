"""Genera archivos de prueba: una referencia (MIDI + WAV) y una "toma" con errores conocidos.

La guitarra se sintetiza con Karplus-Strong (cuerda pulsada), que suena bastante
más a guitarra que una onda seno y le da algo realista a basic-pitch.

Errores plantados en la toma (para verificar que el detector los encuentra):
  - toca más lento (90 vs 100 bpm)
  - nota 6:  un semitono arriba (nota equivocada)
  - nota 13: no se toca (faltante)
  - después de la nota 21: una nota de más
  - nota 27: 120 ms tarde
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

SR = 44100

# Lick en La menor pentatónica: (pitch MIDI), corcheas, 4 compases de 4/4
RIFF = [57, 60, 62, 64, 67, 64, 62, 60,
        57, 60, 62, 64, 67, 69, 67, 64,
        69, 67, 64, 62, 64, 62, 60, 57,
        55, 57, 60, 57, 55, 52, 55, 57]


def pluck(freq: float, dur: float, rng: np.random.Generator, decay: float = 0.996) -> np.ndarray:
    n = int(SR * dur)
    period = max(2, int(round(SR / freq - 0.5)))  # el filtro promediador agrega medio sample
    buf = rng.uniform(-1, 1, period)
    # Karplus-Strong como filtro IIR: y[n] = x[n] + d/2·(y[n-P] + y[n-P+1])
    from scipy.signal import lfilter

    x = np.zeros(n)
    x[:min(period, n)] = buf[:n]
    if n >= period:  # la recurrencia ya toca y[0] en n = P-1; compensamos
        x[period - 1] -= 0.5 * decay * buf[0]
    a = np.zeros(period + 1)
    a[0], a[period - 1], a[period] = 1.0, -0.5 * decay, -0.5 * decay
    out = lfilter([1.0], a, x)
    fade = np.minimum(1, np.linspace(1, 0, n) * 20)  # apagado al final
    return out * fade


def render(notes, total: float, rng) -> np.ndarray:
    y = np.zeros(int(SR * (total + 1.5)))
    for start, end, pitch in notes:
        s = pluck(pretty_midi.note_number_to_hz(pitch), end - start + 0.15, rng)
        a = int(start * SR)
        y[a:a + len(s)] += s * 0.4
    y += rng.normal(0, 0.003, len(y))  # un poco de ruido de fondo
    return (y / np.max(np.abs(y)) * 0.9).astype(np.float32)


def sequence(bpm: float, pitches, lead_in: float = 0.5, jitter: float = 0.0, rng=None):
    eighth = 60 / bpm / 2
    notes = []
    for k, p in enumerate(pitches):
        t = lead_in + k * eighth + (rng.normal(0, jitter) if jitter else 0)
        notes.append([t, t + eighth * 0.9, p])
    # power chord final (A2 E3 A3) de un compás
    t = lead_in + len(pitches) * eighth
    for p in (45, 52, 57):
        notes.append([t, t + 8 * eighth, p])
    return notes


def main(out: Path | str = "demo") -> Path:
    OUT = Path(out)
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)

    # ---- referencia, 100 bpm
    ref = sequence(100, RIFF, lead_in=0.0)
    pm = pretty_midi.PrettyMIDI(initial_tempo=100)
    pm.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0))
    inst = pretty_midi.Instrument(program=25)
    inst.notes = [pretty_midi.Note(100, p, s, e) for s, e, p in ref]
    pm.instruments.append(inst)
    pm.write(str(OUT / "referencia.mid"))
    sf.write(OUT / "referencia.wav", render(ref, ref[-1][1], rng), SR)

    # ---- toma con errores, 90 bpm, 1.2 s de silencio inicial, pequeñas imprecisiones
    take = sequence(90, RIFF, lead_in=1.2, jitter=0.012, rng=rng)
    eighth = 60 / 90 / 2
    take[5][2] += 1                       # nota 6 equivocada
    take[26][0] += 0.12                   # nota 27 tarde
    take[26][1] += 0.12
    extra_t = take[20][0] + eighth * 0.5  # nota de más entre la 21 y la 22
    take.append([extra_t, extra_t + eighth * 0.4, 72])
    del take[12]                          # nota 13 faltante
    sf.write(OUT / "toma.wav", render(sorted(take), max(n[1] for n in take), rng), SR)

    return OUT

