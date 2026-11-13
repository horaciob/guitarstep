"""The web service's jobs (slow work in a worker) and quotas, against a real Postgres (skipped without one)."""
import threading
import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from guitarr import config, jobs, reference
from guitarr.gui.server import app
from tests.test_service import links, signed_in  # noqa: F401 - the fixture


def fake_basic_pitch(monkeypatch):
    """Transcription without the model: two notes, and a count of how many times it ran."""
    ran = []

    def predict(path, model, **k):
        ran.append(path)
        return None, None, [(0.5, 1.0, 64, 0.8, []), (1.0, 1.5, 67, 0.8, [])]
    monkeypatch.setattr(reference, "_quiet_import_basic_pitch", lambda: (predict, None))
    return ran


def a_recording(tmp_path, hz=330.0):
    """A recording of its own (the transcription cache is shared by the tests, keyed by content)."""
    sr = 22050
    t = np.arange(3 * sr) / sr
    p = tmp_path / f"rec-{hz}.wav"
    sf.write(p, (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32), sr)
    return p


def test_a_recording_is_transcribed_by_a_job_then_the_request_goes_through(links, monkeypatch, tmp_path):
    ran = fake_basic_pitch(monkeypatch)
    c = signed_in(links, "ana@example.com")
    assert c.post("/api/songs", files=dict(file=("riff.wav", a_recording(tmp_path, 331.0).read_bytes()))).status_code == 200
    r = c.get("/api/songs/riff.wav/theory")
    assert r.status_code == 202 and r.json()["retry"] is True
    job = r.json()["job"]
    assert job["kind"] == "prepare" and job["status"] == "queued" and not ran        # nothing heavy in the request
    assert c.get("/api/songs/riff.wav/theory").json()["job"]["id"] == job["id"]       # asked again: the same job
    assert jobs.run_next() and not jobs.run_next()
    assert c.get(f"/api/jobs/{job['id']}").json()["status"] == "done" and len(ran) == 1
    assert c.get("/api/songs/riff.wav/theory").status_code == 200                     # ready: no job now
    bob = signed_in(links, "bob@example.com")
    assert bob.get(f"/api/jobs/{job['id']}").status_code == 404                        # not his


def test_analyzing_a_take_is_a_job_with_its_result(links):
    c = signed_in(links, "ana@example.com")
    d = c.post("/api/demo").json()
    import json
    r = c.post("/api/analyze", data=dict(options=json.dumps(dict(song=d["song"], take=d["take"]))))
    assert r.status_code == 202 and r.json()["retry"] is False
    assert jobs.run_next()
    j = c.get(f"/api/jobs/{r.json()['job']['id']}").json()
    assert j["status"] == "done", j
    assert j["result"]["summary"]["score"] > 80 and j["result"]["take_name"] == d["take"]
    assert [h["sessions"] for h in c.get("/api/history").json()] == [1]               # saved as Ana's
    bad = c.post("/api/analyze", data=dict(options=json.dumps(dict(song="nope.mid", take=d["take"]))))
    assert jobs.run_next()
    j = c.get(f"/api/jobs/{bad.json()['job']['id']}").json()
    assert j["status"] == "failed" and j["error"]["code"] == "song_not_found"


def test_one_user_cant_fill_the_queue(links, monkeypatch, tmp_path):
    monkeypatch.setenv("GUITARR_JOBS_PER_USER", "1")
    c = signed_in(links, "ana@example.com")
    for name, hz in (("a.wav", 440.0), ("b.wav", 550.0)):
        c.post("/api/songs", files=dict(file=(name, a_recording(tmp_path, hz).read_bytes())))
    assert c.get("/api/songs/a.wav/theory").status_code == 202
    r = c.get("/api/songs/b.wav/theory")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "too_many_jobs"
    assert signed_in(links, "bob@example.com").post("/api/demo").status_code == 200   # others aren't held up


def test_each_job_runs_once_with_several_workers(links, monkeypatch):
    done = []
    monkeypatch.setitem(jobs.HANDLERS, "slow", lambda args: (time.sleep(0.05), done.append(args["n"]))[1])
    monkeypatch.setenv("GUITARR_JOBS_PER_USER", "20")
    signed_in(links, "ana@example.com")
    import psycopg
    with psycopg.connect(config.os.environ["GUITARR_DATABASE_URL"]) as conn:
        (uid,), = conn.execute("SELECT id::text FROM users").fetchall()
    with config.use_user(uid):
        for n in range(12):
            jobs.enqueue("slow", dict(n=n))
    stop = threading.Event()
    workers = [threading.Thread(target=jobs.work, args=(stop, 0.02)) for _ in range(4)]
    for w in workers:
        w.start()
    t0 = time.time()
    while len(done) < 12 and time.time() - t0 < 10:
        time.sleep(0.02)
    stop.set()
    for w in workers:
        w.join()
    assert sorted(done) == list(range(12))


def test_the_quota_limits_what_a_user_keeps(links, monkeypatch):
    monkeypatch.setenv("GUITARR_QUOTA_MB", "0.01")               # ~10 KB
    c = signed_in(links, "ana@example.com")
    assert c.post("/api/takes", files=dict(file=("small.wav", b"RIFF" * 500))).status_code == 200
    r = c.post("/api/takes", files=dict(file=("big.wav", b"RIFF" * 5000)))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "quota_exceeded"
    assert [t["name"] for t in c.get("/api/takes").json()] == ["small.wav"]
    assert c.get("/api/takes/usage").json()["space"]["quota_mb"] == 0
    assert c.get("/api/auth/me").json()["usage"]["used_mb"] >= 0
