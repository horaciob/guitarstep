"""Análisis de audio en tiempo real: YIN, cromagrama y detector de ataques.

Pipeline por cada bloque (~6 ms):
  ataques por spectral flux (púa) + ataques por cambio de altura (legato:
  hammer-on, pull-off, slide) -> por cada ataque, ~110 ms después:
  altura con YIN (notas sueltas) + cromagrama (acordes).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .core import NOTE_NAMES, note_name

NFFT = 2048
HOP = 256
PITCH_OFF, PITCH_LEN = 0.012, 0.060    # ventana YIN tras el ataque (s)
CHROMA_OFF, CHROMA_LEN = 0.020, 4096   # ventana de cromagrama (s, muestras)
MIN_GAP = 0.07                         # mínimo entre dos ataques (s), por defecto
TRACK_WIN = 2048                       # ventana del seguidor de altura (legato)
TRACK_EVERY = 2                        # cada cuántos hops corre el seguidor
HARMONIC_JUMPS = {12, 19, 24, 28, 31, 36}  # octava, 12va, 2 octavas...
LEGATO_STABLE = 3                      # frames estables para aceptar una altura nueva


def db(x: np.ndarray) -> float:
    return max(-120.0, float(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9))) if len(x) else -120.0


def yin(x: np.ndarray, sr: int, fmin=70.0, fmax=1400.0, thresh=0.3):
    """Altura fundamental (MIDI fraccional) y confianza [0..1], o (None, conf)."""
    x = x.astype(np.float64) - x.mean()
    tau_min, tau_max = int(sr / fmax), int(sr / fmin)
    W = len(x) - tau_max
    if W < tau_max:
        return None, 0.0
    n = 1 << int(np.ceil(np.log2(len(x) + W)))
    acf = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(x[:W], n)), n)[: tau_max + 1]
    cs = np.concatenate([[0.0], np.cumsum(x * x)])
    taus = np.arange(tau_max + 1)
    d = cs[W] + (cs[taus + W] - cs[taus]) - 2 * acf
    cmnd = np.ones_like(d)
    cmnd[1:] = d[1:] * taus[1:] / np.maximum(np.cumsum(d[1:]), 1e-12)
    cand = np.where(cmnd[tau_min:] < thresh)[0]
    if len(cand):
        t = int(cand[0] + tau_min)
        while t + 1 <= tau_max and cmnd[t + 1] < cmnd[t]:
            t += 1
    else:
        t = int(np.argmin(cmnd[tau_min:]) + tau_min)
        if cmnd[t] > 0.45:
            return None, float(1 - cmnd[t])
    shift = 0.0
    if 1 <= t < tau_max:
        a, b, c = cmnd[t - 1], cmnd[t], cmnd[t + 1]
        den = a - 2 * b + c
        if abs(den) > 1e-12:
            shift = 0.5 * (a - c) / den
    f = sr / (t + shift)
    return float(69 + 12 * np.log2(f / 440)), float(1 - cmnd[t])


def chroma(x: np.ndarray, sr: int) -> np.ndarray:
    """Cromagrama (12) a partir de los picos espectrales, normalizado."""
    mag = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    if mag.max() <= 0:
        return np.zeros(12)
    k = np.arange(1, len(mag) - 1)
    peaks = k[(mag[k] > mag[k - 1]) & (mag[k] >= mag[k + 1]) & (mag[k] > 0.05 * mag.max())]
    a, b, c = mag[peaks - 1], mag[peaks], mag[peaks + 1]
    den = a - 2 * b + c
    off = np.where(np.abs(den) > 1e-12, 0.5 * (a - c) / np.where(den == 0, 1, den), 0)
    f = (peaks + off) * sr / len(x)
    sel = (f >= 70) & (f <= 2000)
    pc = np.round(69 + 12 * np.log2(f[sel] / 440)).astype(int) % 12
    out = np.bincount(pc, weights=b[sel], minlength=12)
    return out / (np.linalg.norm(out) + 1e-12)


def chord_template(pitches) -> np.ndarray:
    t = np.zeros(12)
    for p in pitches:
        t[p % 12] += 1.0
        t[(p + 7) % 12] += 0.5   # 3er armónico
        t[(p + 4) % 12] += 0.2   # 5to armónico
    return t / np.linalg.norm(t)


@dataclass
class Detection:
    t: float                 # tiempo del ataque (s, reloj de entrada)
    midi: float | None       # altura YIN (None si no es claramente periódico)
    conf: float
    chroma: np.ndarray = field(repr=False)
    db: float
    legato: bool = False     # ataque detectado por cambio de altura (sin púa)

    def label(self) -> str:
        if self.midi is not None:
            return note_name(int(round(self.midi)))
        top = np.argsort(self.chroma)[::-1][:3]
        return "/".join(NOTE_NAMES[i] for i in top) + " (?)"


class Recorder:
    """Buffer creciente de audio mono (también se guarda al final como WAV)."""

    def __init__(self, sr: int):
        self.sr = sr
        self.data = np.zeros(sr * 60, np.float32)
        self.n = 0

    def append(self, x: np.ndarray) -> None:
        if self.n + len(x) > len(self.data):
            grow = max(len(self.data), len(x))
            self.data = np.concatenate([self.data, np.zeros(grow, np.float32)])
        self.data[self.n:self.n + len(x)] = x
        self.n += len(x)

    def audio(self) -> np.ndarray:
        return self.data[: self.n]


class Detector:
    def __init__(self, rec: Recorder, gate_db: float = -50.0, sensitivity: float = 1.0,
                 min_gap: float = MIN_GAP, legato: bool = True):
        self.rec, self.sr = rec, rec.sr
        self.gate_db = gate_db
        self.delta = 0.012 / max(sensitivity, 1e-3)
        self.min_gap = min_gap
        self.legato = legato
        self.win = np.hanning(NFFT)
        self.nbins = int(4000 / (self.sr / NFFT))
        self.pos = 0
        self.frame = 0
        self.prev = None
        self.flux: list[float] = []   # solo se guardan los últimos frames necesarios
        self.dbs: list[float] = []
        self.flux_off = 0             # índice absoluto del primer elemento de flux/dbs
        self.last_onset = -10 ** 9
        self.last_pick = -10 ** 9     # último ataque de púa (muestra)
        self.pending: list[tuple[int, bool, float | None]] = []  # (muestra, legato, altura)
        self.level_db = -120.0
        self.peak = 0.0
        # seguidor de altura para legato
        self.track_pitch: int | None = None   # altura estable actual
        self.cand_pitch: int | None = None
        self.cand_count = 0
        self.cand_first = 0

    def process(self) -> list[Detection]:
        d = self.rec.data
        while self.pos + NFFT <= self.rec.n:
            fr = d[self.pos:self.pos + NFFT]
            spec = np.log1p(100 * np.abs(np.fft.rfft(fr * self.win))[: self.nbins] / (NFFT / 4))
            self.dbs.append(db(fr))
            self.flux.append(0.0 if self.prev is None else float(np.maximum(spec - self.prev, 0).mean()))
            self.prev = spec
            self._pick()
            if self.legato and self.frame % TRACK_EVERY == 0:
                self._track(fr)
            self.pos += HOP
            self.frame += 1
            if len(self.flux) > 200:  # no crecer sin límite
                cut = len(self.flux) - 100
                del self.flux[:cut], self.dbs[:cut]
                self.flux_off += cut
        out = []
        need = int((max(PITCH_OFF + PITCH_LEN, CHROMA_OFF + CHROMA_LEN / self.sr)) * self.sr)
        while self.pending and self.pending[0][0] + need <= self.rec.n:
            s, leg, hint = self.pending.pop(0)
            a = s + int(PITCH_OFF * self.sr)
            midi, conf = yin(d[a:a + int(PITCH_LEN * self.sr)], self.sr)
            if leg and hint is not None and (midi is None or round(midi) != hint):
                midi, conf = float(hint), max(conf, 0.8)
            if not leg and midi is not None and s == self.last_pick and self.last_onset == s:
                # anclar el seguidor a la altura confirmada del ataque de púa
                self.track_pitch = int(round(midi))
                self.cand_pitch, self.cand_count = None, 0
            c0 = s + int(CHROMA_OFF * self.sr)
            out.append(Detection(s / self.sr, midi, conf, chroma(d[c0:c0 + CHROMA_LEN], self.sr),
                                 db(d[s:s + need]), leg))
        return out

    def _pick(self) -> None:
        """Pico local del flux (evalúa el frame anterior: 1 frame de lookahead)."""
        f = self.flux
        i = len(f) - 2
        if i < 2:
            return
        hist = f[max(0, i - 50):i]
        thr = float(np.median(hist)) + self.delta
        loud = max(self.dbs[i], self.dbs[i + 1]) > self.gate_db
        if f[i] > thr and f[i] > f[i - 1] and f[i] >= f[i + 1] and loud:
            s = (i + self.flux_off) * HOP + NFFT // 2
            if (s - self.last_onset) / self.sr >= self.min_gap:
                self.last_onset = self.last_pick = s
                self.pending.append((s, False, None))
                self.track_pitch = None  # el seguidor se re-engancha a la nota nueva
                self.cand_pitch, self.cand_count = None, 0

    def _track(self, fr: np.ndarray) -> None:
        """Ataques sin púa: la altura salta a otra nota estable sin un pico de flux."""
        if self.pos < self.last_pick + NFFT // 2 + HOP:
            return  # la ventana todavía incluye la nota anterior al ataque
        if self.dbs[-1] < self.gate_db + 6:
            self.track_pitch, self.cand_pitch, self.cand_count = None, None, 0
            return
        w = fr[-TRACK_WIN:] if len(fr) >= TRACK_WIN else fr
        m, conf = yin(w, self.sr, thresh=0.3)
        if m is None or conf < 0.8:
            self.cand_count = 0
            return
        p = int(round(m))
        if p == self.track_pitch or (self.track_pitch is not None
                                     and abs(p - self.track_pitch) in HARMONIC_JUMPS):
            # misma nota, o salto a un (sub)armónico: casi siempre un error de YIN
            self.cand_pitch, self.cand_count = None, 0
            return
        if p != self.cand_pitch:
            self.cand_pitch, self.cand_count = p, 1
            self.cand_first = self.pos + NFFT - TRACK_WIN // 2
            return
        self.cand_count += 1
        if self.cand_count < LEGATO_STABLE:
            return
        prev, self.track_pitch = self.track_pitch, p
        self.cand_pitch, self.cand_count = None, 0
        s = self.cand_first
        if prev is None or (s - self.last_onset) / self.sr < max(self.min_gap, 0.09):
            return  # primera altura tras un ataque de púa: no es legato
        self.last_onset = s
        self.pending.append((s, True, p))

    def update_level(self, block: np.ndarray) -> None:
        if len(block):
            self.level_db = db(block)
            self.peak = max(self.peak * 0.97, float(np.max(np.abs(block))))
