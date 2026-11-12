"""Web UI API (no browser, no audio interface)."""
import json
import time

import pytest

from fastapi.testclient import TestClient

from guitarr.gui.server import app


def client():
    return TestClient(app)


def test_demo_preview_analyze_history():
    c = client()
    assert c.get("/").status_code == 200
    d = c.post("/api/demo").json()
    assert [s["name"] for s in c.get("/api/songs").json()] == [d["song"]]
    pv = c.post("/api/preview", json=dict(song=d["song"], start_bar=2, end_bar=3)).json()
    assert pv["first_bar"] == 2 and pv["last_bar"] == 3 and len(pv["notes"]) == 16
    assert all(n["string"] and n["fret"] is not None for n in pv["notes"])
    r = c.post("/api/analyze", data=dict(options=json.dumps(dict(song=d["song"], take=d["take"]))))
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["summary"]["wrong"] == 1 and res["roll"]["ref"] and res["downbeats"]
    hist = c.get("/api/history").json()
    assert hist and hist[0]["sessions"] == 1
    h = c.get(f"/api/history/{hist[0]['id']}").json()
    assert h["song"] == d["song"] and h["sessions"][0]["kind"] == "file"


def test_live_session_over_api_and_websocket():
    c = client()
    d = c.post("/api/demo").json()
    r = c.post("/api/live/start", json=dict(song=d["song"], mode="tempo", speed=0.9, simulate=d["take"], fast=True))
    assert r.status_code == 200, r.text
    report = None
    with c.websocket_connect("/ws/live") as ws:
        t0 = time.time()
        while time.time() - t0 < 30:
            m = ws.receive_json()
            if m["type"] == "report":
                report = m["report"]
                break
            assert m["type"] == "state"
    assert report and report["summary"]["judged"] == 33
    assert 5 < report["summary"]["played_s"] < 60          # playing time from the detected notes
    assert report["award"]["practice_s"] == 0               # simulated: not added to the plan
    st = c.get("/api/live/state").json()
    assert st["active"] and st["report"]["mode"] == "tempo"


def test_bad_inputs_are_rejected():
    c = client()
    assert c.post("/api/preview", json=dict(song="../../etc/passwd")).status_code in (400, 404)
    assert c.get("/takes/..%2F..%2Fconfig.toml").status_code == 404
    up = c.post("/api/songs", files=dict(file=("x.exe", b"MZ")))
    assert up.status_code == 400


def test_config_api():
    c = client()
    r = c.post("/api/config", json=dict(device="3", channel="2", latency_ms="11.5", gate_db="-55",
                                        sensitivity="", output_device="")).json()
    assert r["saved"] == {"device": 3, "channel": 2, "latency_ms": 11.5, "gate_db": -55.0}


def test_rig_api():
    c = client()
    assert c.get("/api/rig").json() == dict(current=None, presets=[], favorites=[])
    tone = dict(amp=dict(type="crunch", on=True, params=dict(gain=6)), pedals=[], post=[])
    assert c.put("/api/rig/current", json=dict(rig=tone)).status_code == 200
    assert c.get("/api/rig").json()["current"] == tone
    p = c.post("/api/rig/presets", json=dict(name="  My   blues ", rig=tone)).json()
    assert p["name"] == "My blues" and p["id"]
    again = c.post("/api/rig/presets", json=dict(name="my blues", rig={**tone, "pedals": [1]})).json()
    assert again["id"] == p["id"]                       # same name overwrites
    assert len(c.get("/api/rig").json()["presets"]) == 1
    assert c.post("/api/rig/presets", json=dict(name="", rig=tone)).json()["detail"]["code"] == "bad_name"
    assert c.put("/api/rig/current", json=dict(rig="x")).status_code == 400
    assert c.put("/api/rig/current", json=dict(rig=dict(x="a" * 70_000))).json()["detail"]["code"] == "rig_too_big"
    assert c.delete(f"/api/rig/presets/{p['id']}").status_code == 200
    assert c.delete(f"/api/rig/presets/{p['id']}").status_code == 404


def test_rig_impulse_responses():
    import io

    import numpy as np
    import soundfile as sf

    c = client()
    buf = io.BytesIO()
    sf.write(buf, np.r_[1.0, np.zeros(4799)].astype("float32"), 48000, format="WAV")
    r = c.post("/api/rig/irs", files=dict(file=("My cab 4x12.wav", buf.getvalue(), "audio/wav")))
    assert r.status_code == 200 and r.json()["name"] == "My cab 4x12.wav"
    assert [x["name"] for x in c.get("/api/rig/irs").json()] == ["My cab 4x12.wav"]
    assert c.get("/api/rig/irs/My cab 4x12.wav").content == buf.getvalue()
    assert c.get("/api/rig/irs/..%2F..%2Fconfig.toml").status_code in (400, 404)
    assert c.post("/api/rig/irs", files=dict(file=("x.exe", b"MZ"))).json()["detail"]["code"] == "bad_ir"
    assert c.post("/api/rig/irs", files=dict(file=("x.wav", b"not audio"))).json()["detail"]["code"] == "bad_ir"
    long = io.BytesIO()
    sf.write(long, np.zeros(48000 * 4, "float32"), 48000, format="WAV")
    assert c.post("/api/rig/irs", files=dict(file=("long.wav", long.getvalue()))).json()["detail"]["code"] == "ir_too_long"
    assert c.delete("/api/rig/irs/My cab 4x12.wav").status_code == 200
    assert c.get("/api/rig/irs").json() == []


def test_requests_from_other_sites_are_refused():
    c = client()
    # another website open in the browser can't change anything or open a socket
    r = c.put("/api/plan/goal", json=dict(weekly_minutes=300), headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "forbidden_origin"
    assert c.post("/api/backup", files={"file": ("b.zip", b"x")}, headers={"Origin": "null"}).status_code == 403
    # DNS rebinding: a page on evil.example that resolves to 127.0.0.1
    assert c.get("/api/progress", headers={"Host": "evil.example:8765"}).status_code == 403
    # our own page, and tools without a browser, still work
    assert c.get("/api/progress", headers={"Origin": "https://evil.example"}).status_code == 200
    own = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
    assert c.put("/api/plan/goal", json=dict(weekly_minutes=300), headers=own).status_code == 200
    assert c.put("/api/plan/goal", json=dict(weekly_minutes=300)).status_code == 200


def _stream(c, start, wav, chunk=2048, drop=None):
    import numpy as np
    import soundfile as sf
    y, sr = sf.read(wav, dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    with c.websocket_connect("/ws/stream") as ws:
        ws.send_json(dict(type="start", sr=sr, **start))
        assert ws.receive_json()["type"] == "ready"
        for k, i in enumerate(range(0, len(y), chunk)):
            if k != drop:
                ws.send_bytes(i.to_bytes(8, "little") + y[i:i + chunk].astype("<f4").tobytes())
        ws.send_json(dict(type="stop"))
        while True:
            m = ws.receive_json()
            if m["type"] != "state":
                return m


def test_browser_audio_is_graded_like_the_local_input():
    from guitarr.gui.server import song_path, take_path
    from guitarr.reference import RefOptions, load_reference
    from guitarr.session import LiveOptions, LiveSession
    c = client()
    d = c.post("/api/demo").json()
    m = _stream(c, dict(song=d["song"], mode="tempo", speed=0.9), take_path(d["take"]))
    assert m["type"] == "report", m
    local = LiveSession(load_reference(RefOptions(path=song_path(d["song"])), log=lambda m: None),
                        LiveOptions(mode="tempo", speed=0.9, simulate=take_path(d["take"]), fast=True)).run()
    assert m["report"]["summary"] == local["summary"]
    met = m["metrics"]
    assert met["gaps"] == 0 and met["cpu_per_audio_s"] > 0 and met["heard_s"] > 10   # it ends with the song
    # a lost chunk becomes silence: the clock (and the timing of everything after it) stays right
    lost = _stream(c, dict(song=d["song"], mode="tempo", speed=0.9), take_path(d["take"]), drop=40)
    assert lost["metrics"]["gaps"] == 1 and lost["report"]["summary"]["judged"] == 33
    assert lost["report"]["summary"]["timing_mean_ms"] == pytest.approx(local["summary"]["timing_mean_ms"], abs=3)
    assert progress_untouched(c)


def progress_untouched(c):
    return c.get("/api/history").json() == []


def _frames(y, chunk=2048):
    return [i.to_bytes(8, "little") + y[i:i + chunk].astype("<f4").tobytes() for i in range(0, len(y), chunk)]


def test_the_tuner_and_the_signal_check_listen_to_the_browser():
    import numpy as np
    sr = 48000
    t = np.arange(int(1.5 * sr)) / sr
    a2 = (0.3 * np.sin(2 * np.pi * 110.0 * t)).astype(np.float32)
    c = client()
    with c.websocket_connect("/ws/tuner?input=browser") as ws:
        ws.send_json(dict(type="start", sr=sr))
        assert ws.receive_json() == dict(source="browser")
        for f in _frames(a2):
            ws.send_bytes(f)
        for _ in range(100):
            r = ws.receive_json()
            if r.get("note"):
                break
        assert r["note"] == "A2" and r["string"] == 5 and abs(r["cents"]) < 5
    with c.websocket_connect("/ws/signal?input=browser") as ws:
        ws.send_json(dict(type="start", sr=sr))
        assert ws.receive_json() == dict(source="browser", sr=sr)
        quiet = (1e-4 * np.random.default_rng(1).standard_normal(2 * sr)).astype(np.float32)
        for f in _frames(quiet):
            ws.send_bytes(f)
        for _ in range(100):
            if ws.receive_json()["level_db"] < -60:
                break
        r = c.post("/api/signal/measure", json=dict(step="silence", seconds=1.5)).json()
        assert r["floor_db"] < -60
    with c.websocket_connect("/ws/tuner?input=browser") as ws:
        ws.send_json(dict(type="start"))
        assert ws.receive_json()["error"]["code"] == "bad_start"


def test_latency_calibration_with_the_browsers_input():
    """The browser plays the clicks it's given; a cable brings them back 35 ms later. The result is kept for
    that input, and practicing with it uses it instead of the browser's own estimate."""
    import numpy as np
    from guitarr import takeclick
    from guitarr.gui import server
    sr, delay = 48000, 0.035
    c = client()
    r = c.post("/api/calibrate", json=dict(mode="loopback", input="browser", sr=sr, input_name="USB guitar cable")).json()
    assert r["stream"] and r["running"] and len(r["tones"]) == 4
    waves = takeclick.tone_waves(sr, dict(enumerate(r["tones"])), 0.3)
    y = np.zeros(int((r["clicks"][-1][0] + 1.0) * sr), np.float32)
    for t, key in r["clicks"]:
        a = int((t + delay) * sr)
        y[a:a + len(waves[key])] += waves[key]
    with c.websocket_connect("/ws/stream") as ws:
        ws.send_json(dict(type="attach", to="calibrate"))
        assert ws.receive_json()["type"] == "ready"
        for f in _frames(y):
            ws.send_bytes(f)
        while ws.receive_json()["type"] != "ended":
            pass
    res = c.get("/api/calibrate").json()["result"]
    assert res["ok"] and res["method"] == "loopback" and res["spread_ms"] < 2
    assert 25 <= res["latency_ms"] <= 45          # the cable plus the detector's own bias (as test_latency)
    assert res["status"]["input"] == "USB guitar cable"
    d = c.post("/api/demo").json()
    for name, expected in (("USB guitar cable", res["latency_ms"]), ("Another mic", 12.5)):
        assert c.post("/api/live/start", json=dict(song=d["song"], input="browser", sr=sr, input_name=name,
                                                   latency_ms=12.5)).status_code == 200
        assert server.S.session.opts.latency_ms == expected
        c.post("/api/live/stop")
        server.S.thread.join(10)
    # a browser that never sends its input: it ends by itself
    with c.websocket_connect("/ws/stream") as ws:
        ws.send_json(dict(type="attach", to="calibrate"))
        assert ws.receive_json()["detail"]["code"] == "no_session"


def test_browser_audio_needs_a_start_message():
    c = client()
    with c.websocket_connect("/ws/stream") as ws:
        ws.send_json(dict(type="start", song="nope.gp5"))
        assert ws.receive_json()["detail"]["code"] == "bad_start"
