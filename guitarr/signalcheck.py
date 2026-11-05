"""Signal check: measures your guitar input and finds the settings that suit it.

Three measurements, each over a few seconds of the live input:

- silence: strings muted. Noise floor and mains hum (50 or 60 Hz and harmonics).
- strum: strumming hard. Peak level, clipping, and a flat ceiling on the peaks, which means a
  limiter / auto-gain somewhere (interface, USB cable, pedal) squashing the attacks.
- notes: the open strings one at a time, softly. The recording is run through the onset
  detector with a grid of noise gates and sensitivities, and the setting that hears exactly
  the notes you played (no more, no less) wins. It also says how in tune each string was.

A HumFilter (notches at the hum and its harmonics) can then be switched on for every session.
"""
from __future__ import annotations

import io
import threading
from collections import deque

import numpy as np

from .dsp import Detector, Recorder, db, yin

LEVEL_EVERY = 0.05          # s between level readings sent to the page
BUFFER_S = 30               # seconds of input kept for the measurements
TARGET_PEAK = (-18.0, -6.0)  # strumming hard should peak here (dBFS)
GATES = list(range(-78, -26, 4))
SENSITIVITIES = [0.6, 0.8, 1.0, 1.3, 1.6, 2.0, 2.5, 3.0]


# ---------------------------------------------------------------- hum filter
class HumFilter:
    """Notch filters at `hz` and its first harmonics; keeps its state between blocks."""

    def __init__(self, sr: int, hz: int, harmonics: int = 4, q: float = 30.0):
        from scipy.signal import iirnotch, tf2sos

        self.hz = hz
        sos = [tf2sos(*iirnotch(hz * k, q, fs=sr)) for k in range(1, harmonics + 1) if hz * k < sr / 2]
        self.sos = np.vstack(sos)
        self.zi = np.zeros((self.sos.shape[0], 2))

    def __call__(self, block: np.ndarray) -> np.ndarray:
        from scipy.signal import sosfilt

        if not len(block):
            return block
        out, self.zi = sosfilt(self.sos, block, zi=self.zi)
        return out.astype(np.float32)


def hum_filter(sr: int, hz) -> HumFilter | None:
    return HumFilter(sr, int(hz)) if hz in (50, 60, "50", "60") else None


# ---------------------------------------------------------------- live probe
class Probe:
    """Reads the input in a thread, keeps the last seconds and reports levels."""

    def __init__(self, src):
        self.src, self.sr = src, src.sr
        self.buf: deque = deque()
        self.n = 0
        self.lock = threading.Lock()
        self.reading = dict(level_db=-120.0, peak_db=-120.0, clip=False)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        import queue

        self.src.start()
        acc, peak, sq, cnt = 0, 0.0, 0.0, 0
        try:
            while not self._stop.is_set():
                try:
                    blk = self.src.q.get(timeout=0.1)
                except queue.Empty:
                    continue
                if blk is None:
                    break
                with self.lock:
                    self.buf.append(blk)
                    self.n += len(blk)
                    while self.n - len(self.buf[0]) > BUFFER_S * self.sr:
                        self.n -= len(self.buf.popleft())
                peak = max(peak, float(np.max(np.abs(blk))) if len(blk) else 0.0)
                sq += float(np.sum(blk.astype(np.float64) ** 2))
                cnt += len(blk)
                acc += len(blk)
                if acc >= LEVEL_EVERY * self.sr:
                    rms = np.sqrt(sq / max(cnt, 1))
                    self.reading = dict(level_db=round(20 * np.log10(rms + 1e-9), 1),
                                        peak_db=round(20 * np.log10(peak + 1e-9), 1), clip=peak >= 0.99)
                    acc, peak, sq, cnt = 0, 0.0, 0.0, 0
        finally:
            self.src.stop()

    def last(self, seconds: float) -> np.ndarray:
        with self.lock:
            audio = np.concatenate(list(self.buf)) if self.buf else np.zeros(0, np.float32)
        return audio[-int(seconds * self.sr):]


# ---------------------------------------------------------------- measurements
def _frames_db(y: np.ndarray, sr: int, win: float = 0.05) -> np.ndarray:
    hop = max(1, int(win * sr))
    n = len(y) // hop
    if n == 0:
        return np.array([-120.0])
    rms = np.sqrt(np.mean(y[: n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1))
    return 20 * np.log10(rms + 1e-9)


def _band_energy(y: np.ndarray, sr: int, bands) -> tuple[float, float]:
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / sr)
    total = spec[(f > 20) & (f < 5000)].sum() + 1e-18
    sel = np.zeros_like(f, bool)
    for lo, hi in bands:
        sel |= (f >= lo) & (f <= hi)
    return float(spec[sel].sum()), float(total)


def analyze_silence(y: np.ndarray, sr: int) -> dict:
    """Noise floor and mains hum while you don't play."""
    frames = _frames_db(y, sr)
    floor = float(np.percentile(frames, 50))
    best = None
    for hz in (50, 60):
        e, total = _band_energy(y, sr, [(hz * k - 2, hz * k + 2) for k in range(1, 5)])
        if best is None or e > best[1]:
            best = (hz, e, total)
    hz, e, total = best
    share = e / total                              # how much of the noise is hum
    hum_db = 10 * np.log10(e / max(len(y), 1) + 1e-18) + 3   # rough absolute level of the hum
    if floor > -45:
        verdict = "noisy"
    elif floor > -60:
        verdict = "some_noise"
    else:
        verdict = "quiet"
    has_hum = share > 0.3 and floor > -72
    return dict(floor_db=round(floor, 1), hum_hz=hz if has_hum else None, hum_share=round(share, 2),
                hum_db=round(float(hum_db), 1), verdict=verdict)


def analyze_strum(y: np.ndarray, sr: int) -> dict:
    """Level when you strum hard: too low, good, too hot, clipping or squashed by a limiter."""
    a = np.abs(y)
    peak = float(a.max()) if len(a) else 0.0
    peak_db = 20 * np.log10(peak + 1e-9)
    clipped = int(np.sum(a >= 0.99))
    # a clean strum is ~15–20 dB above its sustained level; a limiter or auto-gain squashes
    # the attacks down to a few dB (crest factor)
    frames = _frames_db(y, sr)
    crest = peak_db - float(np.percentile(frames, 90))
    squashed = crest < 10.5 and peak_db > -14
    if clipped > sr * 0.0005:
        verdict = "clipping"
    elif squashed:
        verdict = "limited"
    elif peak_db > TARGET_PEAK[1]:
        verdict = "too_hot"
    elif peak_db < -40:
        verdict = "no_signal"
    elif peak_db < TARGET_PEAK[0]:
        verdict = "too_low"
    else:
        verdict = "good"
    change = 0.0 if verdict == "good" else round(-12 - peak_db, 1)   # dB to move the gain knob
    return dict(peak_db=round(float(peak_db), 1), clipped=clipped, crest_db=round(float(crest), 1),
                verdict=verdict, change_db=float(change))


def _detections(y: np.ndarray, sr: int, gate: float, sens: float):
    rec = Recorder(sr)
    rec.append(y.astype(np.float32))
    det = Detector(rec, gate_db=gate, sensitivity=sens, legato=False)
    out = det.process()
    rec.append(np.zeros(sr, np.float32))           # flush what's pending at the end
    return out + det.process()


def analyze_notes(y: np.ndarray, sr: int, expected: int, tuning: list[int] | None = None,
                  floor_db: float | None = None, hum_hz=None) -> dict:
    """Finds the noise gate and sensitivity that hear exactly the notes you played."""
    filt = hum_filter(sr, hum_hz)
    if filt:
        y = filt(y)
    # a little silence first: the detector needs some history before the first note
    lead = int(0.3 * sr)
    y = np.concatenate([np.zeros(lead, np.float32), y.astype(np.float32)])
    gates = [g for g in GATES if floor_db is None or g >= floor_db + 4] or [GATES[-1]]
    results = []
    for g in gates:
        for s in SENSITIVITIES:
            n = len(_detections(y, sr, g, s))
            results.append((abs(n - expected), abs(s - 1.0), -g, g, s, n))
    results.sort()
    err, _, _, gate, sens, count = results[0]
    # among the exact matches, take the middle of the working gate range (robust both ways)
    exact = sorted(r[3] for r in results if r[0] == err and r[4] == sens)
    if exact:
        gate = exact[len(exact) // 2]
    dets = _detections(y, sr, gate, sens)
    notes = []
    open_strings = sorted(tuning or [])
    for d in dets:
        a = int((d.t + 0.08) * sr)
        midi, conf = yin(y[a:a + int(0.25 * sr)], sr, fmin=40.0)
        if midi is None:
            notes.append(dict(t=round(d.t - lead / sr, 2), midi=None))
            continue
        near = min(open_strings, key=lambda p: abs(p - midi)) if open_strings else None
        notes.append(dict(t=round(d.t - lead / sr, 2), midi=round(midi, 2),
                          string=tuning.index(near) + 1 if near is not None and abs(near - midi) < 0.75 else None,
                          cents=round((midi - near) * 100) if near is not None and abs(near - midi) < 0.75 else None))
    return dict(gate_db=float(gate), sensitivity=float(sens), detected=count, expected=expected,
                exact=err == 0, notes=notes)


def wav_bytes(y: np.ndarray, sr: int) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.clip(y, -1, 1).astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()
