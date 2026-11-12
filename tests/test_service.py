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
    homes = sorted(p.name for p in (config.BASE / "users").iterdir())
    assert len(homes) == 1 and (config.BASE / "users" / homes[0] / "setlists.json").exists()
    # signing in again with another capitalization is the same account
    assert [s["name"] for s in signed_in(links, "ANA@example.com").get("/api/setlists").json()] == ["Ana's gig"]


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
