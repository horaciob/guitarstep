"""Capture your own amp (experimental): fit a drive curve and an 8-band EQ from two recordings of the same
playing, one straight in (DI) and one through the amp. The result loads as the "capture" pedal in the rig.

How it's fitted (a deliberately simple model, written for this app):
1. Align the two recordings (cross-correlation over the first seconds) and trim them to the same length.
2. Drive: saturation flattens peaks, so it lowers the crest factor (peak / RMS). Try drive amounts on the DI
   with the same soft curve the pedal uses and keep the one whose crest factor matches the amp's.
3. EQ: compare the energy per band of the driven DI with the amp's; each band's difference (±12 dB) is its gain.
4. Match: how close the fitted bands get to the amp's spectrum (100 = identical band energies).
"""
from __future__ import annotations

import numpy as np

BANDS = [80, 160, 320, 640, 1250, 2500, 5000, 8000]      # the same bands as the pedal (lib/rig/effects.js)
MAX_SECONDS = 30


class CaptureError(ValueError):
    pass


def _mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=1) if x.ndim > 1 else x


def _resample(x: np.ndarray, sr: int, to: int) -> np.ndarray:
    if sr == to:
        return x
    n = int(round(len(x) * to / sr))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def _align(a: np.ndarray, b: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Shifts b so it lines up with a (up to ±100 ms), then trims both to the same length."""
    n = min(len(a), len(b), sr * 4)
    max_lag = int(0.1 * sr)
    best, lag = -np.inf, 0
    fa = np.fft.rfft(a[:n], 2 * n)
    fb = np.fft.rfft(b[:n], 2 * n)
    xc = np.fft.irfft(fa * np.conj(fb))
    for k in range(-max_lag, max_lag + 1):
        v = xc[k % (2 * n)]
        if v > best:
            best, lag = v, k
    if lag > 0:
        a = a[lag:]
    elif lag < 0:
        b = b[-lag:]
    m = min(len(a), len(b))
    return a[:m], b[:m]


def _crest(x: np.ndarray) -> float:
    rms = np.sqrt(np.mean(x ** 2)) or 1e-9
    return float(np.percentile(np.abs(x), 99.9) / rms)


def _band_energy(x: np.ndarray, sr: int) -> np.ndarray:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    edges = [0] + [np.sqrt(BANDS[i] * BANDS[i + 1]) for i in range(len(BANDS) - 1)] + [sr / 2]
    return np.array([spec[(freqs >= lo) & (freqs < hi)].sum() + 1e-12 for lo, hi in zip(edges, edges[1:])])


def fit(di: np.ndarray, amp: np.ndarray, sr_di: int, sr_amp: int) -> dict:
    """→ {drive_db, bands: {freq: dB}, match, params} where params are the capture pedal's knobs."""
    sr = 44100
    a = _resample(_mono(di), sr_di, sr)[: sr * MAX_SECONDS]
    b = _resample(_mono(amp), sr_amp, sr)[: sr * MAX_SECONDS]
    if len(a) < sr // 2 or len(b) < sr // 2:
        raise CaptureError("too_short")
    if np.sqrt(np.mean(a ** 2)) < 1e-4 or np.sqrt(np.mean(b ** 2)) < 1e-4:
        raise CaptureError("silent")
    a, b = _align(a, b, sr)
    a = a / (np.sqrt(np.mean(a ** 2)) or 1) * 0.08          # about a guitar's level into a pedal
    target = _crest(b)
    best_db, best_err = 0.0, np.inf
    for db in np.arange(0, 30.5, 0.5):
        y = np.tanh(a * 10 ** (db / 20))
        err = abs(_crest(y) - target)
        if err < best_err:
            best_db, best_err = float(db), err
    driven = np.tanh(a * 10 ** (best_db / 20))
    ea, eb = _band_energy(driven, sr), _band_energy(b, sr)
    ea, eb = ea / ea.sum(), eb / eb.sum()                  # compare shapes, not loudness
    diff = 10 * np.log10(eb / ea)
    diff -= np.median(diff)
    gains = np.clip(diff, -12, 12)
    resid = np.abs(diff - gains)
    match = int(round(max(0.0, 100 - 8 * float(np.mean(resid)) - 4 * best_err)))
    params = dict(drive=round(best_db / 3, 1), level=5.0, **{f"c{f}": round(float(g) * 2) / 2 for f, g in zip(BANDS, gains)})
    return dict(drive_db=best_db, bands={str(f): round(float(g), 1) for f, g in zip(BANDS, gains)}, match=match, params=params)
