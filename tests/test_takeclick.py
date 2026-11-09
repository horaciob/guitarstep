"""Listening back to a take with the metronome you heard: clicks saved beside the take, mixed in on request."""
import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from guitarr import config, takeclick
from guitarr.gui.server import app

SR = 44100


def make_take(name="take-20260101-120000.wav", seconds=3.0):
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    p = config.TAKES_DIR / name
    t = np.arange(int(seconds * SR)) / SR
    sf.write(p, (0.2 * np.sin(2 * np.pi * 110 * t)).astype(np.float32), SR)
    return p


def test_clicks_are_saved_beside_the_take_and_mixed_in():
    p = make_take()
    assert takeclick.info(p) == dict(click=False, bpm=None, final_bpm=None)
    assert takeclick.save(p, [], bpm=70) is None                         # no metronome, nothing saved
    takeclick.save(p, [(0.5, True), (1.357, False), (2.214, False)], bpm=70, final_bpm=70)
    assert takeclick.info(p) == dict(click=True, bpm=70, final_bpm=70)
    audio, _ = sf.read(p, dtype="float32")
    mixed = takeclick.mix(audio, SR, takeclick.load(p)["clicks"])
    assert len(mixed) == len(audio)
    a = int(0.5 * SR)
    assert np.abs(mixed[a:a + 200] - audio[a:a + 200]).max() > 0.05      # the click is there, on time
    assert np.allclose(mixed[:a - 10], audio[:a - 10])                  # and nothing else changed
    assert np.max(np.abs(mixed)) <= 0.99
    quiet = takeclick.mix(audio * 0.01, SR, [(0.5, True)])
    assert 0.05 < np.max(np.abs(quiet)) < 0.2                           # audible over a quiet take, not deafening


def test_take_endpoint_with_and_without_the_click():
    c = TestClient(app)
    p = make_take()
    clean = c.get(f"/takes/{p.name}").content
    assert c.get(f"/takes/{p.name}?click=1").content == clean             # no clicks saved: the take as is
    takeclick.save(p, [(1.0, True)], bpm=90)
    r = c.get(f"/takes/{p.name}?click=1")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    mixed, sr = sf.read(io.BytesIO(r.content), dtype="float32")
    assert sr == SR and len(mixed) == int(3.0 * SR)
    assert c.get(f"/takes/{p.name}").content == clean                    # the take itself stays clean
    row = next(x for x in c.get("/api/takes").json() if x["name"] == p.name)
    assert row["click"] is True and row["bpm"] == 90
    assert not any(x["name"].endswith(".json") for x in c.get("/api/takes").json())


def test_a_tempo_session_saves_its_clicks_with_the_take(monkeypatch):
    """The real session path, with a fake input and a fake metronome (no audio device is opened)."""
    import queue

    from guitarr import catalog, session
    from guitarr.reference import RefOptions, load_reference

    class FakeMic:
        def __init__(self, *a, **k):
            self.sr, self.name, self.overflows, self.adc0, self.q = SR, "fake", 0, 0.0, queue.Queue()

        def start(self):
            for _ in range(int(6 * SR / 1024)):                       # 6 s of a quiet string, then the end
                self.q.put((0.05 * np.sin(2 * np.pi * 110 * np.arange(1024) / SR)).astype(np.float32))
            self.q.put(None)

        def stop(self):
            pass

    class FakeMetronome:
        def __init__(self, *a, **k):
            pass

        start = stop = lambda self: None

    monkeypatch.setattr(session, "MicSource", FakeMic)
    monkeypatch.setattr(session, "Metronome", FakeMetronome)
    ref = load_reference(RefOptions(chart=catalog.get_chart("01-em-am")))
    s = session.LiveSession(ref, session.LiveOptions(mode="tempo", speed=0.5, latency_ms=20, count_extras=False))
    rep = s.run()
    take = config.TAKES_DIR / rep["take"].split("/")[-1]
    d = takeclick.load(take)
    assert rep["take_info"] == dict(click=True, bpm=35.0, final_bpm=35.0)          # 70 BPM chart at 50%
    times = [t for t, _ in d["clicks"]]
    assert times[0] == 1.02 and d["clicks"][0][1] is True                          # 1 s lead-in + 20 ms latency, accented
    assert all(abs(b - a - 60 / 35) < 1e-3 for a, b in zip(times, times[1:]))      # one click per beat
    assert times[-1] < 6.0                                                          # only inside the recording
