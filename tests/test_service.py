"""The web service: accounts, one data folder per user, and audio from the browser
(against a real Postgres; skipped without one)."""
import time

import pytest
from fastapi.testclient import TestClient

from guitarr import accounts, config
from guitarr.db import migrate
from guitarr.gui.server import app


@pytest.fixture
def links(pg_url, monkeypatch):
    """Service mode on a fresh, migrated database; returns the sign-in links "sent" so far."""
    monkeypatch.setenv("GUITARR_DATABASE_URL", pg_url)
    migrate.migrate(pg_url, log=lambda m: None)
    sent = {}
    monkeypatch.setattr(accounts, "send_link", lambda email, url: sent.__setitem__(email, url))
    return sent


def token_of(link):
    return link.split("token=")[1]


def signed_in(links, email):
    c = TestClient(app)
    assert c.post("/api/auth/link", json=dict(email=email)).status_code == 200
    assert c.post("/api/auth/verify", json=dict(token=token_of(links[email]))).status_code == 200
    assert c.get("/api/auth/me").json()["user"]["email"].lower() == email.lower()
    return c


def test_everything_needs_a_signed_in_user(links):
    c = TestClient(app)
    r = c.get("/api/progress")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "not_signed_in"
    assert "signinForm" in c.get("/").text                     # the sign-in page instead of the app
    assert c.get("/api/status").json()["service"] is True
    assert c.post("/api/auth/link", json=dict(email="nope")).json()["detail"]["code"] == "bad_email"
    with pytest.raises(Exception):
        with c.websocket_connect("/ws/live") as ws:
            ws.receive_json()


def test_sign_in_link_works_once_and_sign_out_ends_the_session(links):
    c = signed_in(links, "ana@example.com")
    assert "signinForm" not in c.get("/").text
    again = TestClient(app).post("/api/auth/verify", json=dict(token=token_of(links["ana@example.com"])))
    assert again.json()["detail"]["code"] == "bad_link"
    assert c.post("/api/auth/signout").status_code == 200
    assert c.get("/api/progress").status_code == 401


def test_opening_a_link_only_shows_whose_it_is(links):
    """A link someone else sent you (or a mail scanner opening it) signs nobody in by itself."""
    mine, other = TestClient(app), TestClient(app)
    mine.post("/api/auth/link", json=dict(email="eve@example.com"))
    link = links["eve@example.com"]
    page = other.get(link.replace("http://testserver", ""))
    assert page.status_code == 200 and "confirmForm" in page.text
    assert other.get("/api/progress").status_code == 401                  # opening it didn't sign in
    tok = token_of(link)
    assert other.get(f"/api/auth/link?token={tok}").json() == dict(email="eve@example.com", same_browser=False)
    assert mine.get(f"/api/auth/link?token={tok}").json()["same_browser"] is True
    assert other.get("/api/auth/link?token=nope").json()["detail"]["code"] == "bad_link"
    assert mine.post("/api/auth/verify", json=dict(token=tok)).status_code == 200   # still unused
    assert mine.get("/api/progress").status_code == 200


def test_a_link_made_on_the_console(links, monkeypatch, capsys):
    """`guitarr user link EMAIL` (make login): no mail server needed; the account exists before the first sign-in."""
    from guitarr import admin, cli
    monkeypatch.setenv("GUITARR_PUBLIC_URL", "http://localhost:9999")
    cli.main(["user", "link", "dev@example.com"])
    link = capsys.readouterr().out.strip().splitlines()[-1]
    assert link.startswith("http://localhost:9999/auth/verify?token=") and links == {}
    assert "dev@example.com" in [u["email"] for u in admin.overview()["users"]]
    c = TestClient(app)
    tok = token_of(link)
    assert c.get(f"/api/auth/link?token={tok}").json() == dict(email="dev@example.com", same_browser=True)
    assert c.post("/api/auth/verify", json=dict(token=tok)).status_code == 200
    assert c.get("/api/auth/me").json()["user"]["email"] == "dev@example.com"


def test_too_many_links_are_refused(links):
    c = TestClient(app)
    for _ in range(accounts.LINKS_PER_HOUR):
        assert c.post("/api/auth/link", json=dict(email="b@example.com")).status_code == 200
    r = c.post("/api/auth/link", json=dict(email="B@example.com"))
    assert r.json()["detail"]["code"] == "too_many_links"


def test_each_user_has_their_own_data(links):
    ana, bob = signed_in(links, "ana@example.com"), signed_in(links, "bob@example.com")
    assert ana.post("/api/setlists", json=dict(name="Ana's gig")).status_code == 200
    assert [s["name"] for s in ana.get("/api/setlists").json()] == ["Ana's gig"]
    assert bob.get("/api/setlists").json() == []
    assert ana.get("/api/status").json()["home"] is None        # no server paths for the users
    assert ana.get("/api/settings/sources").json()["home"]["value"] is None
    assert not (config.BASE / "users").exists() or not list((config.BASE / "users").glob("*/setlists.json"))
    # signing in again with another capitalization is the same account
    assert [s["name"] for s in signed_in(links, "ANA@example.com").get("/api/setlists").json()] == ["Ana's gig"]


def _db(pg_url, sql, *args):
    import psycopg
    with psycopg.connect(pg_url) as conn:
        return conn.execute(sql, args).fetchall()


CHART = "title: Two chords\nbpm: 90\n\n| Em | Am |\n"


def test_user_data_lives_in_the_database(links, pg_url):
    from guitarr import history
    ana = signed_in(links, "ana@example.com")
    assert ana.post("/api/setlists", json=dict(name="Gig")).status_code == 200
    assert ana.post("/api/config", json=dict(gate_db=-61)).status_code == 200
    assert ana.post("/api/charts", json=dict(text=CHART)).json()["id"] == "two-chords"
    (uid,), = _db(pg_url, "SELECT id::text FROM users WHERE email = 'ana@example.com'")
    with config.use_user(uid):
        history.save(dict(kind="live", reference=dict(path="song.mid", name="Song"), summary=dict(score=80)))
    docs = {n for n, in _db(pg_url, "SELECT name FROM user_documents WHERE user_id = %s", uid)}
    assert {"setlists", "config"} <= docs
    assert ana.get("/api/config").json()["audio"]["gate_db"] == -61
    assert [c["id"] for c in ana.get("/api/charts").json() if c.get("mine")] == ["two-chords"]
    assert [(h["id"], h["sessions"], h["last_score"]) for h in ana.get("/api/history").json()] == [("song", 1, 80)]
    assert ana.get("/api/history/song").json()["sessions"][0]["score"] == 80
    home = config.user_home(uid)
    assert not any((home / f).exists() for f in ("setlists.json", "config.toml", "history", "charts"))
    # nobody else sees it
    bob = signed_in(links, "bob@example.com")
    assert bob.get("/api/history").json() == [] and not [c for c in bob.get("/api/charts").json() if c.get("mine")]
    assert bob.delete("/api/charts/two-chords").status_code != 200
    assert ana.delete("/api/charts/two-chords").status_code == 200
    assert not _db(pg_url, "SELECT 1 FROM user_charts")


def test_files_from_before_the_database_are_moved_in(links, pg_url):
    """A user's data kept as files (phase 1) is moved into the database the first time it's read."""
    import json
    c = signed_in(links, "old@example.com")
    (uid,), = _db(pg_url, "SELECT id::text FROM users WHERE email = 'old@example.com'")
    home = config.user_home(uid)
    (home / "history" / "song").mkdir(parents=True)
    (home / "history" / "song" / "20250101-120000-000000-live.json").write_text(json.dumps(
        dict(kind="live", date="2025-01-01T12:00:00", reference=dict(name="Song"), summary=dict(score=70))))
    (home / "charts").mkdir()
    (home / "charts" / "old-one.txt").write_text(CHART)
    (home / "setlists.json").write_text(json.dumps([dict(id="x", name="Old gig", items=[])]))
    (home / "config.toml").write_text("[audio]\ngate_db = -55.0\n")
    assert [s["name"] for s in c.get("/api/setlists").json()] == ["Old gig"]
    assert c.get("/api/config").json()["audio"]["gate_db"] == -55
    assert [h["sessions"] for h in c.get("/api/history").json()] == [1]
    assert "old-one" in [x["id"] for x in c.get("/api/charts").json() if x.get("mine")]
    assert (home / "setlists.json.imported").exists() and (home / "history.imported").is_dir()
    assert [h["sessions"] for h in c.get("/api/history").json()] == [1]      # moved once


def test_a_backup_moves_between_accounts(links, pg_url):
    from guitarr import history
    ana = signed_in(links, "ana@example.com")
    ana.post("/api/setlists", json=dict(name="Gig"))
    ana.post("/api/charts", json=dict(text=CHART))
    (uid,), = _db(pg_url, "SELECT id::text FROM users WHERE email = 'ana@example.com'")
    with config.use_user(uid):
        history.save(dict(kind="live", reference=dict(path="song.mid", name="Song"), summary=dict(score=80)))
    zipped = ana.get("/api/backup").content
    bob = signed_in(links, "bob@example.com")
    for _ in range(2):                                   # restoring twice doesn't double the history
        r = bob.post("/api/backup", files=dict(file=("b.zip", zipped, "application/zip")))
        assert r.status_code == 200, r.text
    assert [s["name"] for s in bob.get("/api/setlists").json()] == ["Gig"]
    assert [h["sessions"] for h in bob.get("/api/history").json()] == [1]
    assert "two-chords" in [c["id"] for c in bob.get("/api/charts").json() if c.get("mine")]


def _add_xp(url, home, uid, n):
    """In another process (like a worker): n practices of 20 XP for one user."""
    import os
    os.environ["GUITARR_DATABASE_URL"] = url
    from pathlib import Path

    from guitarr import config, progress
    config.BASE = Path(home)
    with config.use_user(uid):
        for _ in range(n):
            progress.add_practice(100)


def test_processes_writing_the_same_progress_lose_nothing(links, pg_url):
    """The app and the workers are different processes: each read-modify-write holds the document's lock."""
    import multiprocessing as mp
    signed_in(links, "ana@example.com")
    (uid,), = _db(pg_url, "SELECT id::text FROM users WHERE email = 'ana@example.com'")
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_add_xp, args=(pg_url, str(config.BASE), uid, 15)) for _ in range(3)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    (data,), = _db(pg_url, "SELECT data FROM user_documents WHERE user_id = %s AND name = 'progress'", uid)
    assert data["xp"] >= 3 * 15 * 20             # weekly challenges can add bonus XP on top, never less


def test_health_and_tidying_up(links, pg_url):
    from guitarr import db, jobs
    c = TestClient(app)
    assert c.get("/api/health").json() == dict(ok=True)              # no sign-in needed
    c.post("/api/auth/link", json=dict(email="old@example.com"))
    _db(pg_url, "UPDATE login_tokens SET expires_at = now() - interval '2 days' RETURNING 1")
    with db.pool().connection() as conn:
        jobs.tidy(conn)
    assert not _db(pg_url, "SELECT 1 FROM login_tokens")


def test_the_servers_own_audio_is_off_limits(links):
    c = signed_in(links, "ana@example.com")
    assert c.post("/api/calibrate", json={}).json()["detail"]["code"] == "bad_sample_rate"    # the browser's input instead
    assert c.get("/api/config").json()["path"] is None
    assert c.get("/api/devices").json()["browser"] is True
    d = c.post("/api/demo").json()
    r = c.post("/api/live/start", json=dict(song=d["song"], mode="wait"))
    assert r.json()["detail"]["code"] == "bad_sample_rate"


def test_practice_with_audio_from_the_browser(links):
    import soundfile as sf
    c = signed_in(links, "ana@example.com")
    d = c.post("/api/demo").json()
    wav, = (config.BASE / "users").glob(f"*/takes/{d['take']}")     # in Ana's own folder
    y, sr = sf.read(wav, dtype="float32")
    r = c.post("/api/live/start", json=dict(song=d["song"], mode="tempo", speed=0.9, sr=sr, click=True))
    assert r.status_code == 200, r.text
    assert r.json()["stream"] is True
    clicks = []
    with c.websocket_connect("/ws/stream") as ws:
        ws.send_json(dict(type="attach"))
        assert ws.receive_json()["type"] == "ready"
        for i in range(0, len(y), 2048):
            ws.send_bytes(i.to_bytes(8, "little") + y[i:i + 2048].astype("<f4").tobytes())
        ws.send_json(dict(type="stop"))
        while True:
            m = ws.receive_json()
            if m["type"] == "clicks":
                clicks += m["clicks"]
            elif m["type"] == "ended":
                break
    assert clicks and clicks[0][0] >= 1.0 and clicks[0][1] is True     # the count-in, to play in the browser
    t0 = time.time()
    while time.time() - t0 < 20 and not c.get("/api/live/state").json().get("report"):
        time.sleep(0.1)
    rep = c.get("/api/live/state").json()["report"]
    assert rep["summary"]["judged"] == 33 and rep["award"]
    assert [h["sessions"] for h in c.get("/api/history").json()] == [1]  # it counts: it's this user's practice
    # someone else can't feed (or see) Ana's session
    bob = signed_in(links, "bob@example.com")
    assert bob.get("/api/live/state").json() == dict(active=False)
