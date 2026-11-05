"""Signal check: noise, hum, level and the onset settings search, on synthetic guitars."""
import numpy as np
import pytest

from guitarr import signalcheck as sc
from guitarr.core import TUNINGS

SR = 48000


def pluck(midi, dur=1.0, amp=0.3, seed=0):
    """Karplus-Strong string, like a clean electric guitar."""
    rng = np.random.default_rng(seed + midi)
    f = 440 * 2 ** ((midi - 69) / 12)
    p = int(round(SR / f))
    buf = rng.uniform(-1, 1, p)
    out = np.zeros(int(dur * SR))
    for i in range(len(out)):
        j = i % p
        out[i] = buf[j]
        buf[j] = 0.996 * 0.5 * (buf[j] + buf[(j + 1) % p])
    return amp * out


def hum(seconds, level=0.01, hz=50):
    t = np.arange(int(seconds * SR)) / SR
    return level * (np.sin(2 * np.pi * hz * t) + 0.5 * np.sin(2 * np.pi * 2 * hz * t) + 0.3 * np.sin(2 * np.pi * 3 * hz * t))


def noise(seconds, level=1e-4, seed=1):
    return level * np.random.default_rng(seed).standard_normal(int(seconds * SR))


def test_silence_quiet_and_humming():
    quiet = sc.analyze_silence(noise(3, 1e-5), SR)
    assert quiet["verdict"] == "quiet" and quiet["hum_hz"] is None
    humming = sc.analyze_silence(noise(3, 1e-4) + hum(3, 0.01, 60), SR)
    assert humming["hum_hz"] == 60 and humming["hum_share"] > 0.9 and humming["verdict"] == "noisy"


def test_strum_levels():
    chord = sum(pluck(m, 2.0) for m in TUNINGS["standard"])
    def at(peak_db):
        y = np.tile(chord, 3)
        return y / np.abs(y).max() * 10 ** (peak_db / 20)
    assert sc.analyze_strum(at(-12), SR)["verdict"] == "good"
    low = sc.analyze_strum(at(-30), SR)
    assert low["verdict"] == "too_low" and low["change_db"] == pytest.approx(18, abs=0.5)
    assert sc.analyze_strum(at(-3), SR)["verdict"] == "too_hot"
    assert sc.analyze_strum(np.clip(at(6), -1, 1), SR)["verdict"] == "clipping"
    squashed = np.tanh(8 * at(-6)) * 0.7          # a hard limiter: every attack hits the ceiling
    assert sc.analyze_strum(squashed, SR)["verdict"] == "limited"
    assert sc.analyze_strum(noise(3, 1e-4), SR)["verdict"] == "no_signal"


def test_notes_search_finds_settings_and_tuning():
    tuning = TUNINGS["standard"]
    gap = np.zeros(int(0.3 * SR))
    played = [m for m in reversed(tuning)]          # 6th string to 1st
    detuned = {50: 0.3}                             # the D string 30 cents sharp
    parts = []
    for k, m in enumerate(played):
        f_m = m + detuned.get(m, 0.0)
        parts += [pluck(int(m), 1.2, amp=0.08) if f_m == m else _pluck_f(f_m, 1.2, 0.08), gap]
    y = np.concatenate(parts) + noise(len(np.concatenate(parts)) / SR, 3e-4)
    r = sc.analyze_notes(y, SR, expected=6, tuning=tuning, floor_db=-65)
    assert r["exact"] and r["detected"] == 6
    strings = [n["string"] for n in r["notes"]]
    assert strings == [6, 5, 4, 3, 2, 1]
    d = next(n for n in r["notes"] if n["string"] == 4)
    assert 20 <= d["cents"] <= 40


def _pluck_f(midi_f, dur, amp):
    # a pluck at a fractional pitch (resampled from a whole-note pluck)
    base = pluck(int(round(midi_f)), dur * 1.1, amp)
    ratio = 2 ** ((midi_f - round(midi_f)) / 12)
    idx = np.arange(int(dur * SR)) * ratio
    return np.interp(idx, np.arange(len(base)), base)


def test_hum_filter_removes_hum_and_keeps_the_guitar():
    y = pluck(45, 1.0, 0.2) + hum(1.0, 0.05, 50)
    out = sc.HumFilter(SR, 50)(y.astype(np.float32))
    e_in, _ = sc._band_energy(y[SR // 2:], SR, [(48, 52), (98, 102)])
    e_out, _ = sc._band_energy(out[SR // 2:], SR, [(48, 52), (98, 102)])
    assert e_out < e_in / 100                           # −20 dB or more on the hum
    g_in, _ = sc._band_energy(y[SR // 2:], SR, [(105, 115)])     # A2 = 110 Hz survives
    g_out, _ = sc._band_energy(out[SR // 2:], SR, [(105, 115)])
    assert g_out > g_in * 0.5
    assert sc.hum_filter(SR, None) is None and sc.hum_filter(SR, "60").hz == 60


class _FakeProbe:
    def __init__(self, audio):
        self.sr, self.audio = SR, audio.astype(np.float32)

    def last(self, seconds):
        return self.audio[-int(seconds * SR):]


def test_signal_api_measures_applies_and_plays_back():
    from fastapi.testclient import TestClient

    from guitarr import config
    from guitarr.gui import server

    c = TestClient(server.app)
    server.S.probe, server.S.signal = None, {}                 # start clean (other tests may have used it)
    assert c.post("/api/signal/measure", json=dict(step="silence")).json()["detail"]["code"] == "no_probe"
    server.S.probe = _FakeProbe(noise(4, 1e-4) + hum(4, 0.01, 50))
    try:
        sil = c.post("/api/signal/measure", json=dict(step="silence", seconds=3)).json()
        assert sil["hum_hz"] == 50
        lead = np.zeros(SR // 2)
        notes = np.concatenate([lead] + [np.concatenate([pluck(m, 1.2, 0.08), np.zeros(SR // 3)]) for m in reversed(TUNINGS["standard"])])
        server.S.probe = _FakeProbe(notes + hum(len(notes) / SR + 1, 0.002, 50)[:len(notes)])
        r = c.post("/api/signal/measure", json=dict(step="notes", seconds=len(notes) / SR, expected=6)).json()
        assert r["detected"] == 6, r
        wav = c.get("/api/signal/clip/notes")
        assert wav.status_code == 200 and wav.content[:4] == b"RIFF"
        assert c.post("/api/signal/measure", json=dict(step="nope")).status_code == 400
        a = c.post("/api/signal/apply", json=dict(gate_db=r["gate_db"], sensitivity=r["sensitivity"], hum_hz=50)).json()["audio"]
        assert a["hum_hz"] == 50 and a["gate_db"] == r["gate_db"]
        c.post("/api/signal/apply", json=dict(hum_hz=None))
        assert "hum_hz" not in config.load()["audio"]
    finally:
        server.S.probe, server.S.signal = None, {}
