"""Capture your amp (roadmap G80): the fit recovers a known drive and EQ from synthetic recordings."""
import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from guitarr import capture
from guitarr.gui.server import app


def guitarish(sr=44100, seconds=3, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(sr * seconds) / sr
    x = sum(np.sin(2 * np.pi * f * t) * rng.uniform(0.2, 1) for f in (110, 165, 220, 330, 440, 660))
    env = np.exp(-((t % 0.5) * 6))                         # plucks every half second
    return x * env / 6


def test_fit_finds_more_drive_for_a_dirtier_amp():
    x = guitarish()
    clean = capture.fit(x, np.tanh(x * 0.08 / np.sqrt(np.mean(x ** 2)) * 1.5), 44100, 44100)
    dirty = capture.fit(x, np.tanh(x * 0.08 / np.sqrt(np.mean(x ** 2)) * 25), 44100, 44100)
    assert dirty["drive_db"] > clean["drive_db"] + 10
    assert set(dirty["params"]) == {"drive", "level", *[f"c{f}" for f in capture.BANDS]}
    assert all(-12 <= dirty["params"][f"c{f}"] <= 12 for f in capture.BANDS)


def test_fit_sees_an_eq_tilt_and_a_delay():
    x = guitarish()
    y = np.convolve(np.tanh(x * 0.08 / np.sqrt(np.mean(x ** 2)) * 4), [1, -0.95])[: len(x)]   # treble boost
    y = np.concatenate([np.zeros(300), y])[: len(x)]                                           # 7 ms later
    r = capture.fit(x, y, 44100, 44100)
    assert r["bands"]["8000"] > r["bands"]["160"]
    assert 0 <= r["match"] <= 100


def test_capture_endpoint_and_errors():
    x = guitarish(seconds=1)

    def wav(a):
        b = io.BytesIO()
        sf.write(b, a, 44100, format="WAV")
        return b.getvalue()
    c = TestClient(app)
    r = c.post("/api/rig/capture", files=dict(di=("di.wav", wav(x)), amp=("amp.wav", wav(np.tanh(x * 3)))))
    assert r.status_code == 200 and "drive" in r.json()["params"]
    r = c.post("/api/rig/capture", files=dict(di=("di.wav", wav(np.zeros(44100))), amp=("amp.wav", wav(x))))
    assert r.json()["detail"]["code"] == "capture_silent"
    r = c.post("/api/rig/capture", files=dict(di=("di.wav", b"nope"), amp=("amp.wav", wav(x))))
    assert r.json()["detail"]["code"] == "bad_audio"


def test_rig_saves_from_many_threads_lose_nothing():
    """The autosave of the current sound and saving presets run in parallel requests."""
    from concurrent.futures import ThreadPoolExecutor

    from guitarr import rig

    def work(i):
        rig.save_current({"n": i})
        rig.save_preset(f"Sound {i}", {"n": i})

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(work, range(40)))
    names = {p["name"] for p in rig.get()["presets"]}
    assert names == {f"Sound {i}" for i in range(40)}
    assert not list(rig.path().parent.glob("*.tmp")) and not list(rig.path().parent.glob(".*.tmp"))


def test_favorite_sounds_are_kept():
    from fastapi.testclient import TestClient

    from guitarr import rig
    from guitarr.gui.server import app
    c = TestClient(app)
    assert c.get("/api/rig").json()["favorites"] == []
    r = c.put("/api/rig/favorites", json=dict(favorites=["angus_crunch", "surf", "surf"]))
    assert r.json()["favorites"] == ["angus_crunch", "surf"]
    assert rig.get()["favorites"] == ["angus_crunch", "surf"]
    assert c.put("/api/rig/favorites", json=dict(favorites="surf")).json()["detail"]["code"] == "bad_favorites"
    assert c.put("/api/rig/favorites", json=dict(favorites=["../x"])).json()["detail"]["code"] == "bad_favorites"
