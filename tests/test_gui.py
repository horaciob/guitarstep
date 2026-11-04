"""API de la interfaz gráfica (sin navegador ni placa de audio)."""
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
