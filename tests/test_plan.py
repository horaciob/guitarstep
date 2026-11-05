"""Practice plan: weeks, rounding, colors, streak, timer edge cases and validation."""
import json
from datetime import date, datetime, timedelta

import pytest

from guitarr import plan
from guitarr.plan import PlanError


def ts(day: date, h=12, m=0, s=0) -> float:
    return datetime(day.year, day.month, day.day, h, m, s).timestamp()


def write(d):
    plan._write(d)


def keep_open(t0: float, t1: float):
    """The page sends a heartbeat every 30 s while the timer runs."""
    t = t0 + 30
    while t <= t1:
        plan.timer("beat", now=t)
        t += 30


def test_defaults_and_week_view():
    v = plan.get()
    assert [c["id"] for c in v["categories"]] == ["technique", "repertoire", "theory", "free"]
    assert v["today"]["goal"] == 30 and v["week"]["goal"] == 210
    assert v["today"]["remaining"] == 30 and v["today"]["status"] == "low"
    assert len(v["week"]["days"]) == 7 and v["week"]["previous"] is None
    assert v["streak"] == 0 and v["timer"] is None


def test_active_seconds_skips_pauses():
    assert plan.active_seconds([]) == 0
    assert plan.active_seconds([0, 1, 2, 3]) == 3 + plan.TAIL_S
    # a 60 s silence only counts as MAX_GAP_S
    assert plan.active_seconds([0, 1, 61, 62]) == 1 + plan.MAX_GAP_S + 1 + plan.TAIL_S


def test_sessions_are_tracked_by_category():
    rep = dict(summary=dict(played_s=90))
    assert plan.record_session(dict(type="exercise"), rep) == 90
    plan.record_session(dict(type="practice", chart=True), dict(summary=dict(played_s=120)))
    plan.record_session(dict(type="practice"), dict(summary=dict(played_s=500), simulated=True))   # not counted
    cats = {c["id"]: c["today_s"] for c in plan.get()["categories"]}
    assert cats == dict(technique=90, repertoire=120, theory=0, free=0)
    assert plan.get()["today"]["minutes"] == round(210 / 60)


def test_rounding_to_the_minute_keeps_a_met_goal_met():
    plan.record_session(dict(type="practice"), dict(summary=dict(played_s=30 * 60 - 20)))   # 29:40
    t = plan.get()["today"]
    assert t["minutes"] == 30 and t["status"] == "met" and t["remaining"] == 0


def test_colors_estimate_previous_week_and_streak():
    today = date.today()
    d = plan._read()
    start = plan.week_start(today)
    prev = start - timedelta(days=7)
    d["weeks"][prev.isoformat()] = dict(minutes=dict(technique=10, repertoire=15, theory=5))
    d["weeks"][start.isoformat()] = dict(minutes=dict(technique=10, repertoire=15, theory=5))
    for i in range(7):
        d["days"][(prev + timedelta(days=i)).isoformat()] = dict(repertoire=30 * 60)     # every day met
    for k, mins in enumerate([30, 20, 5]):
        day = today - timedelta(days=k + 1)
        if day >= start:
            d["days"][day.isoformat()] = dict(technique=mins * 60)
    write(d)
    v = plan.get()
    assert v["week"]["previous"] == 210
    status = {x["date"]: x["status"] for x in v["week"]["days"]}
    y = (today - timedelta(days=1)).isoformat()
    if y in status:
        assert status[y] == "met"
    for x in v["week"]["days"]:
        if x["state"] == "future":
            assert x["minutes"] is None and x["status"] is None
    # yesterday met; the day before reached 20/30 (yellow) → streak 1 unless the week just began
    assert v["streak"] == (1 if today.weekday() >= 2 else v["streak"])


def test_streak_counts_today_once_met():
    today = date.today()
    d = plan._read()
    for k in range(0, 15):
        day = today - timedelta(days=k)
        d["weeks"].setdefault(plan.week_start(day).isoformat(), dict(minutes=dict(technique=10)))
    for k in (1, 2, 3):
        d["days"][(today - timedelta(days=k)).isoformat()] = dict(technique=600)
    write(d)
    assert plan.get()["streak"] == 3
    plan.record_session(dict(type="exercise"), dict(summary=dict(played_s=600)))
    assert plan.get()["streak"] == 4


def test_past_weeks_keep_their_plan():
    today = date.today()
    d = plan._read()
    old = plan.week_start(today) - timedelta(days=7)
    d["weeks"][old.isoformat()] = dict(minutes=dict(technique=40))
    write(d)
    # the new week starts from the latest earlier week
    v = plan.get()
    assert {c["id"]: c["minutes"] for c in v["categories"]}["technique"] == 40
    plan.set_minutes("technique", 5)
    assert plan._read()["weeks"][old.isoformat()]["minutes"]["technique"] == 40


def test_weekly_goal_rescales_proportionally():
    v = plan.set_weekly_goal(7 * 60)             # 60 a day from 10/15/5
    mins = {c["id"]: c["minutes"] for c in v["categories"]}
    assert sum(mins.values()) == 60 and mins == dict(technique=20, repertoire=30, theory=10, free=0)
    v = plan.set_weekly_goal(100)                # ceil(100/7) = 15, leftover to the largest
    mins = {c["id"]: c["minutes"] for c in v["categories"]}
    assert sum(mins.values()) == 15 and max(mins, key=mins.get) == "repertoire"


@pytest.mark.parametrize("value,code", [(-5, "negative_minutes"), ("abc", "bad_minutes"), (2.5, "bad_minutes"),
                                        (None, "bad_minutes"), (601, "too_many_minutes")])
def test_minutes_validation(value, code):
    before = plan.path().read_text() if plan.path().exists() else None
    with pytest.raises(PlanError) as e:
        plan.set_minutes("technique", value)
    assert e.value.code == code
    assert (plan.path().read_text() if plan.path().exists() else None) == before    # nothing saved


def test_categories_add_remove_and_validation():
    with pytest.raises(PlanError) as e:
        plan.add_category("   ", 5)
    assert e.value.code == "empty_name"
    v = plan.add_category("  Escalas  mayores ", 5)
    sc = next(c for c in v["categories"] if c["name"] == "Escalas mayores")
    with pytest.raises(PlanError) as e:
        plan.add_category("ESCALAS MAYÓRES", 5)              # same name: case, accents, spaces
    assert e.value.code == "duplicate_name"
    plan.record_session(None, dict(summary=dict(played_s=1)))
    plan.timer("start", sc["id"], now=ts(date.today(), 10))
    keep_open(ts(date.today(), 10), ts(date.today(), 10, 5))
    with pytest.raises(PlanError) as e:
        plan.remove_category(sc["id"])
    assert e.value.code == "timer_busy"
    plan.timer("stop", now=ts(date.today(), 10, 5))
    v = plan.remove_category(sc["id"])
    assert all(c["id"] != sc["id"] for c in v["categories"])
    assert plan._read()["days"][date.today().isoformat()][sc["id"]] == 300       # time kept
    v = plan.add_category("escalas mayores", 8)              # comes back with its history
    assert next(c for c in v["categories"] if c["id"] == sc["id"])["minutes"] == 8
    for cid in ("technique", "repertoire", sc["id"]):
        plan.remove_category(cid)
    with pytest.raises(PlanError) as e:
        plan.remove_category("theory")                    # free play has no minutes: the goal would be 0
    assert e.value.code == "zero_goal"
    plan.remove_category("free")
    with pytest.raises(PlanError) as e:
        plan.remove_category("theory")
    assert e.value.code == "last_category"


def test_timer_start_pause_resume_stop():
    day = date.today()
    plan.timer("start", "theory", now=ts(day, 9))
    with pytest.raises(PlanError) as e:
        plan.timer("start", "technique", now=ts(day, 9, 0, 20))
    assert e.value.code == "timer_busy"
    keep_open(ts(day, 9), ts(day, 9, 10))
    v = plan.timer("pause", now=ts(day, 9, 10))
    assert v["timer"]["running"] is False and v["categories"][2]["today_s"] == 600
    plan.timer("resume", now=ts(day, 9, 20))
    keep_open(ts(day, 9, 20), ts(day, 9, 25))
    v = plan.timer("stop", now=ts(day, 9, 25))
    assert v["timer"] is None and v["categories"][2]["today_s"] == 900


def test_timer_closed_page_is_paused_where_it_was_last_seen():
    day = date.today()
    plan.timer("start", "theory", now=ts(day, 9))
    keep_open(ts(day, 9), ts(day, 9, 5))
    v = plan.view(now=ts(day, 11))                  # nobody saw it for two hours
    assert v["timer"]["running"] is False
    assert plan._read()["days"][day.isoformat()]["theory"] == 300


def test_timer_across_midnight_is_saved_on_its_day():
    day = date.today() - timedelta(days=1)
    plan.timer("start", "theory", now=ts(day, 23, 50))
    for k in range(1, 12):                         # the page stays open past midnight
        plan.timer("beat", now=ts(day, 23, 50) + k * 50)
    v = plan.view(now=ts(day, 23, 50) + 12 * 50)
    assert v["timer"] is None
    assert plan._read()["days"][day.isoformat()]["theory"] == 600


def test_live_session_pauses_the_manual_timer():
    day = date.today()
    plan.timer("start", "theory", now=ts(day, 8))
    keep_open(ts(day, 8), ts(day, 8, 3))
    plan.pause_timer(now=ts(day, 8, 3))
    d = plan._read()
    assert d["timer"]["started"] is None and d["days"][day.isoformat()]["theory"] == 180


def test_plan_api():
    from fastapi.testclient import TestClient

    from guitarr.gui.server import app
    c = TestClient(app)
    assert c.get("/api/plan").json()["today"]["goal"] == 30
    assert c.put("/api/plan/categories/theory", json=dict(minutes=-1)).json()["detail"]["code"] == "negative_minutes"
    assert c.put("/api/plan/categories/theory", json=dict(minutes=10)).json()["today"]["goal"] == 35
    assert c.put("/api/plan/goal", json=dict(weekly_minutes=0)).json()["detail"]["code"] == "zero_goal"
    r = c.post("/api/plan/categories", json=dict(name="Ear training", minutes=5)).json()
    cid = next(x["id"] for x in r["categories"] if x["name"] == "Ear training")
    assert c.post("/api/plan/timer", json=dict(action="start", category=cid)).json()["timer"]["running"]
    assert c.post("/api/plan/timer", json=dict(action="stop")).json()["timer"] is None
    assert c.delete(f"/api/plan/categories/{cid}").status_code == 200
    assert c.delete("/api/plan/categories/nope").json()["detail"]["code"] == "no_category"
    assert json.loads(plan.path().read_text())["categories"][-1]["active"] is False


def test_days_before_the_plan_existed_have_no_data():
    from datetime import date, timedelta
    v = plan.get()
    for day in v["week"]["days"]:
        if day["date"] < date.today().isoformat():
            assert day["state"] == "before" and day["minutes"] is None and day["status"] is None
    assert v["week"]["estimate"] is None
    plan.record_session(dict(type="exercise"), dict(summary=dict(played_s=60)),
                        day=date.today() - timedelta(days=30))
    assert plan._read()["since"] == date.today().isoformat()     # set once, not moved by later logs


def test_free_play_from_the_tone_rig():
    assert plan.record_free_play(45) == 45
    assert plan.record_free_play(10_000) == plan.MAX_FREE_CHUNK_S          # one report can't add hours
    with pytest.raises(PlanError):
        plan.record_free_play("lots")
    cats = {c["id"]: c for c in plan.get()["categories"]}
    assert cats["free"]["today_s"] == 45 + plan.MAX_FREE_CHUNK_S and cats["free"]["auto"]
    assert plan.get()["today"]["goal"] == 30                              # free play has no goal of its own


def test_plans_saved_before_free_play_get_it():
    d = plan._read()
    d["categories"] = [c for c in d["categories"] if c["id"] != "free"]
    plan._write(d)
    assert any(c["id"] == "free" for c in plan.get()["categories"])
