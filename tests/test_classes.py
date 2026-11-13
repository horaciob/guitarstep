"""Classes (a teacher, students, assignments) and the admin page of the web service (against a real Postgres)."""
from guitarr import config, history
from tests.test_service import CHART, _db, links, signed_in  # noqa: F401 - the fixture


def uid(pg_url, email):
    (u,), = _db(pg_url, "SELECT id::text FROM users WHERE lower(email) = %s", email)
    return u


def test_a_teacher_invites_sees_the_week_and_sends_assignments(links, pg_url):
    teo, ana, bob = (signed_in(links, f"{n}@example.com") for n in ("teo", "ana", "bob"))
    inv = teo.post("/api/class/invite").json()
    assert "#/class?join=" in inv["url"]
    assert ana.get(f"/api/class/invite/{inv['code']}").json() == dict(teacher="teo@example.com", yours=False, joined=False)
    assert teo.post("/api/class/join", json=dict(code=inv["code"])).json()["detail"]["code"] == "own_class"
    assert ana.post("/api/class/join", json=dict(code=inv["code"])).json() == dict(teacher="teo@example.com")
    assert ana.post("/api/class/join", json=dict(code="nope")).json()["detail"]["code"] == "bad_invite"
    a = uid(pg_url, "ana@example.com")
    with config.use_user(a):
        history.save(dict(kind="live", reference=dict(path="song.mid", name="Song"), summary=dict(score=80)))
    # the teacher sees Ana's week, not Bob's (he isn't in the class)
    c = teo.get("/api/class").json()
    assert [s["email"] for s in c["students"]] == ["ana@example.com"] and c["students"][0]["week"]["songs"] == 1
    assert teo.get(f"/api/class/students/{a}/report").json()["songs"][0]["name"] == "Song"
    assert teo.get(f"/api/class/students/{uid(pg_url, 'bob@example.com')}/report").json()["detail"]["code"] == "not_your_student"
    assert bob.get(f"/api/class/students/{a}/report").status_code == 400
    assert [t["email"] for t in ana.get("/api/class").json()["teachers"]] == ["teo@example.com"]
    # an assignment: one of the teacher's setlists, with his own chart inside
    teo.post("/api/charts", json=dict(text=CHART))
    sl = teo.post("/api/setlists", json=dict(name="This week")).json()
    teo.put(f"/api/setlists/{sl['id']}", json=dict(items=[dict(kind="chart", id="two-chords")]))
    sent = teo.post(f"/api/class/students/{a}/assignments", json=dict(setlist=sl["id"], note="Verse at 80")).json()
    assert sent["name"] == "This week"
    inbox = ana.get("/api/class").json()["inbox"]
    assert [(i["teacher"], i["name"], i["note"], i["items"]) for i in inbox] == [("teo@example.com", "This week", "Verse at 80", 1)]
    r = ana.post(f"/api/class/assignments/{inbox[0]['id']}", json=dict(accept=True)).json()
    assert r["accepted"] and r["setlist"]["name"] == "This week"
    assert "two-chords" in [x["id"] for x in ana.get("/api/charts").json() if x.get("mine")]     # the chart came along
    assert ana.get("/api/class").json()["inbox"] == []
    assert teo.get("/api/class").json()["students"][0]["sent"][0]["state"] == "accepted"
    assert ana.post(f"/api/class/assignments/{inbox[0]['id']}", json=dict(accept=True)).json()["detail"]["code"] == "no_assignment"
    # leaving ends the sharing
    t = uid(pg_url, "teo@example.com")
    assert ana.delete(f"/api/class/teachers/{t}").status_code == 200
    assert teo.get(f"/api/class/students/{a}/report").json()["detail"]["code"] == "not_your_student"
    assert teo.post(f"/api/class/students/{a}/assignments", json=dict(setlist=sl["id"])).status_code == 400


def test_the_admin_page_and_blocking(links, pg_url, monkeypatch):
    monkeypatch.setenv("GUITARR_ADMINS", "Boss@example.com, other@example.com")
    boss, ana = signed_in(links, "boss@example.com"), signed_in(links, "ana@example.com")
    assert boss.get("/api/auth/me").json()["user"]["admin"] is True
    assert ana.get("/api/auth/me").json()["user"]["admin"] is False
    assert ana.get("/api/admin").json()["detail"]["code"] == "not_admin"
    o = boss.get("/api/admin").json()
    assert o["totals"]["users"] == 2 and set(o["jobs"]) == {"queued", "running", "done", "failed"}
    a = next(u for u in o["users"] if u["email"] == "ana@example.com")
    assert boss.post(f"/api/admin/users/{uid(pg_url, 'boss@example.com')}", json=dict(blocked=True)).json()["detail"]["code"] == "block_self"
    assert boss.post(f"/api/admin/users/{a['id']}", json=dict(blocked=True)).status_code == 200
    assert ana.get("/api/progress").status_code == 401                       # signed out everywhere
    ana.post("/api/auth/link", json=dict(email="ana@example.com"))
    tok = links["ana@example.com"].split("token=")[1]
    assert ana.post("/api/auth/verify", json=dict(token=tok)).json()["detail"]["code"] == "blocked"
    assert boss.post(f"/api/admin/users/{a['id']}", json=dict(blocked=False)).status_code == 200
    assert signed_in(links, "ana@example.com").get("/api/progress").status_code == 200
