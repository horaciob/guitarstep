"""Interface and usability (roadmap H): next steps, settings sources, stats totals, today's queue."""
from fastapi.testclient import TestClient

from guitarr import catalog, progress, routine
from guitarr.gui.server import app


def prog(**kw):
    return {**progress._empty(), **kw}


def test_next_step_suggestions():
    ns = catalog.next_step
    assert ns("major-scale", "g-position", dict(passed=False, score=None, need=80), prog())["code"] == "not_heard"
    assert ns("major-scale", "g-position", dict(passed=False, score=30, need=80), prog())["code"] == "retry_with_help"
    assert ns("major-scale", "g-position", dict(passed=False, score=70, need=80), prog()) == dict(code="almost", params=dict(missing=10))
    assert ns("intervals", "interval-frets-quiz", dict(passed=False, score=50, need=80), prog())["code"] == "quiz_retry"
    assert ns("first-change", "em-am-chart", dict(passed=False, score=20, need=80), prog())["code"] == "retry_slower"
    assert ns("major-scale", "g-position", dict(passed=True, score=90, need=80), prog()) == dict(code="less_help", params=dict(level=1))
    p = prog(guidance={"major-scale/g-position": 2})
    assert ns("major-scale", "g-position", dict(passed=True, score=90, need=80), p)["code"] == "try_variation"
    p["variations"] = {"major-scale/g-position": 90}
    n = ns("major-scale", "g-position", dict(passed=True, score=90, need=80), p)
    assert n["code"] == "next_exercise" and n["params"]["exercise"] == "c-one-string"
    n = ns("major-scale", "g-position", dict(passed=True, score=90, need=80, lesson_done=True), p)
    assert n == dict(code="next_lesson", params=dict(lesson="spelling", title="The major scale in all 12 keys"))
    assert ns("major-scale", "g-position", dict(passed=True, variant=True), p)["code"] == "variant_done"


def test_quiz_award_carries_the_next_step():
    from guitarr import quiz
    c = TestClient(app)
    d = c.post("/api/exercise/draw", json=dict(lesson="intervals", exercise="interval-frets-quiz")).json()
    r = c.post("/api/exercise/finish", json=dict(token=d["token"])).json()                 # nothing answered
    assert r["award"]["next"]["code"] == "quiz_retry"


def test_settings_sources():
    c = TestClient(app)
    s = c.get("/api/settings/sources").json()
    assert s["tuning"] == dict(value="standard", source="default")
    assert s["home"]["source"] in ("env", "default") and s["home"]["env"] == "GUITARR_HOME"
    c.put("/api/instrument", json=dict(tuning="drop_d"))
    assert c.get("/api/settings/sources").json()["tuning"] == dict(value="drop_d", source="saved")


def test_stats_totals_and_queue():
    c = TestClient(app)
    t = c.get("/api/stats").json()["totals"]
    assert set(t) >= {"songs", "sessions", "streak", "minutes", "active_days"}
    r = c.post("/api/today/queue", json=dict(ref="chart:25-song-form-aaba", section="B")).json()
    q = next(s for s in r["steps"] if s["kind"] == "queued")
    assert q["route"] == "#/practice?chart=25-song-form-aaba&from=17&to=24" and q["params"]["section"] == "B"
    assert c.post("/api/today/queue", json=dict(ref="nope", section="B")).json()["detail"]["code"] == "bad_queue"
    r = c.delete("/api/today/queue", params=dict(ref="chart:25-song-form-aaba", section="B")).json()
    assert not any(s["kind"] == "queued" for s in r["steps"])
    for i in range(progress.QUEUE_MAX):
        progress.queue_add("chart:25-song-form-aaba", f"s{i}")
    assert c.post("/api/today/queue", json=dict(ref="chart:25-song-form-aaba", section="extra")).json()["detail"]["code"] == "queue_full"
    assert c.delete("/api/today/queue").json()["steps"][0]["kind"] == "tune"
    assert progress.get()["queue"] == []
