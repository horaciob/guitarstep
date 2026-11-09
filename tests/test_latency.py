"""Is it you or the system: latency measurements (cable vs playing along) and the verdict on a take's timing."""
import queue

import numpy as np
from fastapi.testclient import TestClient

from guitarr import config, latency, takeclick, tuner
from guitarr.gui.server import app


def test_verdict_tells_a_steady_offset_from_a_human_one():
    v = latency.verdict
    assert v([-120, -130], None) is None                                       # too few hits to say
    steady = [-111, -148, -168, -125, -177, -145, -112, -154]                  # a real take: early, and even
    r = v(steady, "play")
    assert r["code"] == "steady_system" and r["params"]["dir"] == "early" and 130 <= r["params"]["ms"] <= 150
    assert v(steady, "loopback")["code"] == "steady_you"                       # measured with a cable: it's you
    assert v([-101, -9, -147, -23, -97, 192, 129, 40], "play")["code"] == "unsteady"
    assert v([-30, -35, -40, -28, -33], None)["code"] == "slight"
    r = v([5, -8, 12, -3, 0, 7], None)
    assert r["code"] == "on_time" and r["params"]["n"] == 6


def test_cable_measures_the_system_and_playing_along_measures_you():
    st = latency.record("play", -13.3, 20, "Volt 2", "MacBook Pro Speakers")
    assert st["applied_ms"] == -13.3 and st["method"] == "play" and st["tendency_ms"] is None
    codes = {w["code"] for w in st["warnings"]}
    assert codes == {"two_devices", "negative"}
    st = latency.record("loopback", 24.0, 0.4, "Volt 2", "Volt 2")
    assert st["applied_ms"] == 24.0 and st["method"] == "loopback" and st["warnings"] == []
    st = latency.record("play", -16.0, 18, "Volt 2", "Volt 2")                # now it's your habit, not the system
    assert st["applied_ms"] == 24.0 and st["tendency_ms"] == -40.0
    assert config.load()["audio"]["latency_ms"] == 24.0
    assert {w["code"] for w in latency.status("Volt 2", "MacBook Pro Speakers")["warnings"]} == {"two_devices", "devices_changed"}
    st = latency.record("play", 30.0, 18, "Volt 2", "MacBook Pro Speakers")    # other devices: the cable number no longer applies
    assert st["applied_ms"] == 30.0 and st["method"] == "play" and st["system_ms"] is None


def test_endpoint_reports_status():
    c = TestClient(app)
    s = c.get("/api/latency").json()
    assert {"applied_ms", "method", "tendency_ms", "warnings"} <= set(s)
    config.update_audio(latency_ms=-13.3)                                     # an old setup: no record of how it was measured
    assert "negative" in {w["code"] for w in latency.status("Volt 2", "Volt 2")["warnings"]}


def test_a_beat_sized_correction_is_flagged():
    latency.record("loopback", 492.0, 1.3, "Volt 2", "Volt 2")
    assert "too_large" in {w["code"] for w in latency.status("Volt 2", "Volt 2")["warnings"]}


def _fakes(monkeypatch, delay, noise=0.0, plain=False):
    """A fake interface whose input gets back the metronome's clicks `delay` s later (a cable), and nothing else."""
    sr = 48000
    k = {}

    class Mic:
        def __init__(self, *a, **k):
            self.sr, self.name, self.overflows, self.adc0, self.q = sr, "fake", 0, 0.0, queue.Queue()

        def start(self):
            pass

        def stop(self):
            pass

    class Metro:
        def __init__(self, dev, src, clicks, **kw):
            self.src, self.clicks = src, clicks
            k.update(kw)

        def start(self):
            n = int((self.clicks[-1][0] + delay + 1.0) * sr)
            x = np.zeros(n, np.float32)
            tones = None if plain else k.get("tones")
            waves = takeclick.tone_waves(sr, tones, 0.3) if tones else takeclick.click_waves(sr, 0.3)
            rng = np.random.default_rng(1)
            for t, acc in self.clicks:
                a = int((t + delay + rng.normal(0, noise)) * sr)
                w = waves[acc if tones else acc == 0]
                x[a:a + len(w)] += w
            for i in range(0, n, 256):
                self.src.q.put(x[i:i + 256])

        def stop(self):
            pass

    import guitarr.audio_io as aio
    monkeypatch.setattr(aio, "MicSource", Mic)
    monkeypatch.setattr(aio, "Metronome", Metro)


def test_loopback_calibration_finds_the_cable_delay(monkeypatch):
    _fakes(monkeypatch, 0.025)
    r = tuner.calibrate(0, 2, loopback=True)
    assert r["ok"] and r["method"] == "loopback" and r["spread_ms"] < 2
    assert 15 <= r["latency_ms"] <= 35                     # 25 ms of cable delay plus the detector's own bias


def test_loopback_slightly_early_isnt_taken_for_the_previous_click(monkeypatch):
    _fakes(monkeypatch, -0.012)                            # the driver over-reports its latency by 12 ms
    r = tuner.calibrate(0, 2, loopback=True)
    assert r["ok"] and -25 <= r["latency_ms"] <= 0         # not ~490 (the click before, one beat at 120 BPM)


def test_loopback_longer_than_a_beat_is_still_the_same_click(monkeypatch):
    _fakes(monkeypatch, 0.6)                               # more than a beat at 120 BPM: tone tells which click it is
    r = tuner.calibrate(0, 2, loopback=True)
    assert r["ok"] and 590 <= r["latency_ms"] <= 615


def test_loopback_ignores_sounds_that_arent_its_clicks(monkeypatch):
    _fakes(monkeypatch, 0.02, plain=True)                  # something else comes back (the ordinary 1000/1600 Hz click)
    r = tuner.calibrate(0, 2, loopback=True)
    assert not r["ok"] and r["code"] == "loop_other_sound" and r["heard"] >= 10 and r["channel"] == 2


def test_loopback_with_nothing_coming_back(monkeypatch):
    _fakes(monkeypatch, 30.0)                              # clicks never arrive while it listens
    r = tuner.calibrate(0, 2, loopback=True)
    assert not r["ok"] and r["code"] == "no_loop" and r["heard"] == 0 and r["peak_db"] < -100
    assert (config.CACHE_DIR / "cable-test.wav").exists()  # kept, to check what came back
