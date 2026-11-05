"""Backup and restore of ~/.guitarr."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from guitarr import backup, config, plan, progress
from guitarr.gui.server import app


def make_data(home):
    plan.add_category("Scales", 5)
    progress.add_practice(90)
    (home / "songs").mkdir(parents=True, exist_ok=True)
    (home / "songs" / "a.mid").write_bytes(b"MThd")
    (home / "takes").mkdir(parents=True, exist_ok=True)
    (home / "takes" / "t.wav").write_bytes(b"RIFF" * 100)
    (home / "cache" / "x").mkdir(parents=True, exist_ok=True)
    (home / "cache" / "x" / "big.npz").write_bytes(b"0" * 100)


def names(data):
    return set(zipfile.ZipFile(io.BytesIO(data)).namelist())


def test_backup_contents(home):
    make_data(home)
    n = names(backup.create())
    assert {"plan.json", "progress.json", "songs/a.mid", backup.MANIFEST} <= n
    assert not any(x.startswith(("takes/", "cache/")) for x in n)
    assert "takes/t.wav" in names(backup.create(takes=True))


def test_restore_round_trip_with_safety_copy(home):
    make_data(home)
    data = backup.create()
    plan.add_category("Arpeggios", 5)                       # changed after the backup
    (home / "songs" / "a.mid").write_bytes(b"changed")
    r = backup.restore(data)
    assert r["restored"] >= 3 and r["safety_copy"].startswith("before-restore-")
    assert (home / "songs" / "a.mid").read_bytes() == b"MThd"
    assert all(c["name"] != "Arpeggios" for c in plan.get()["categories"])
    assert (home / "backups" / r["safety_copy"]).exists()


@pytest.mark.parametrize("bad", ["../evil.txt", "/etc/passwd", "cache/x.npz", "notes.txt", "songs/../../x"])
def test_restore_rejects_unexpected_paths(home, bad):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(backup.MANIFEST, "{}")
        z.writestr(bad, "x")
    with pytest.raises(backup.BackupError) as e:
        backup.restore(buf.getvalue())
    assert e.value.code == "bad_backup"
    assert not (home.parent / "evil.txt").exists()


def test_restore_rejects_other_files(home):
    with pytest.raises(backup.BackupError):
        backup.restore(b"not a zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("progress.json", "{}")                   # no manifest: not ours
    with pytest.raises(backup.BackupError):
        backup.restore(buf.getvalue())


def test_backup_api(home):
    make_data(home)
    c = TestClient(app)
    r = c.get("/api/backup?takes=true")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "takes/t.wav" in names(r.content)
    m = json.loads(zipfile.ZipFile(io.BytesIO(r.content)).read(backup.MANIFEST))
    assert m["app"] == "guitarr" and m["takes"] is True
    up = c.post("/api/backup", files=dict(file=("b.zip", r.content, "application/zip")))
    assert up.status_code == 200 and up.json()["restored"] > 0
    bad = c.post("/api/backup", files=dict(file=("b.zip", b"nope", "application/zip")))
    assert bad.json()["detail"]["code"] == "bad_backup"
