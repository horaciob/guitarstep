"""Web UI API (no browser, no audio interface)."""
import json
import time

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
