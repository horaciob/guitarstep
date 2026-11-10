"""Recorded takes: how much room they use, clearing old ones, and the backup's safety copies."""
import os
import time

from fastapi.testclient import TestClient

from guitarr import backup, config, takeclick, takes
from guitarr.gui.server import app

DAY = 86400


def make(name, days_old, size=1000):
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    p = config.TAKES_DIR / name
    p.write_bytes(b"x" * size)
    takeclick.click_path(p).write_text("{}")
    t = time.time() - days_old * DAY
    os.utime(p, (t, t))
    return p


def test_usage_and_cleanup():
    old, mid, new = make("a.wav", 100), make("b.wav", 40), make("c.wav", 1)
    u = takes.usage()
    assert u["count"] == 3 and u["bytes"] == 3000
    assert u["older"]["30"]["count"] == 2 and u["older"]["90"]["count"] == 1 and u["older"]["0"]["count"] == 3
    r = takes.cleanup(30)
    assert r["deleted"] == 2 and r["freed"] == 2000 and r["count"] == 1
    assert not old.exists() and not takeclick.click_path(old).exists() and not mid.exists() and new.exists()


def test_cleanup_api():
    make("a.wav", 10)
    c = TestClient(app)
    assert c.get("/api/takes/usage").json()["count"] == 1
    assert c.post("/api/takes/cleanup", json=dict(days=3)).json()["detail"]["code"] == "bad_days"
    assert c.post("/api/takes/cleanup", json=dict(days=7)).json()["deleted"] == 1
    assert c.get("/api/takes").json() == []


def test_restore_keeps_only_the_last_safety_copies():
    (config.HOME / "progress.json").parent.mkdir(parents=True, exist_ok=True)
    (config.HOME / "progress.json").write_text("{}")
    folder = config.HOME / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (folder / f"before-restore-2020-01-0{i + 1}-000000.zip").write_bytes(b"old")
    backup.restore(backup.create())
    kept = sorted(p.name for p in folder.glob("before-restore-*.zip"))
    assert len(kept) == backup.KEEP_SAFETY and not kept[0].startswith("before-restore-2020-01-01")


def test_a_deleted_take_answers_404_to_head():
    c = TestClient(app)
    make("here.wav", 1)
    assert c.head("/takes/here.wav").status_code == 200
    assert c.head("/takes/gone.wav").status_code == 404
