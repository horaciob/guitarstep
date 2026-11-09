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


def _fakes(monkeypatch, delay, noise=0.0):
    """A fake interface whose input gets back the metronome's clicks `delay` s later (a cable), and nothing else."""
    sr = 48000

    class Mic:
        def __init__(self, *a, **k):
            self.sr, self.name, self.overflows, self.adc0, self.q = sr, "fake", 0, 0.0, queue.Queue()

        def start(self):
            pass

        def stop(self):
            pass

    class Metro:
        def __init__(self, dev, src, clicks, **k):
            self.src, self.clicks = src, clicks

        def start(self):
            n = int((self.clicks[-1][0] + delay + 1.0) * sr)
            x = np.zeros(n, np.float32)
            waves = takeclick.click_waves(sr, 0.3)
            rng = np.random.default_rng(1)
            for t, acc in self.clicks:
                a = int((t + delay + rng.normal(0, noise)) * sr)
                x[a:a + len(waves[acc])] += waves[acc]
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


def test_loopback_with_nothing_coming_back(monkeypatch):
    _fakes(monkeypatch, 5.0)                               # clicks never arrive in the window
    r = tuner.calibrate(0, 2, loopback=True)
    assert not r["ok"] and r["code"] == "no_loop"
