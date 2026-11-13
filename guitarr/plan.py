"""Practice plan: daily minutes per category, time tracked by playing, and a weekly view.

- A week runs Monday to Sunday. Each week keeps its own minutes per category, so changing
  the plan only affects the current week; past weeks stay as they were.
- The daily goal is the sum of the category minutes; the weekly goal is 7 × that. Changing
  the plan mid-week keeps the goal the days already gone had (they're frozen first).
- Time is counted on its own while you play with the listener (exercises, chord checks and
  drills → technique; songs and charts → repertoire). It counts *playing* time: pauses longer
  than a few seconds between notes are left out. A manual timer covers everything else
  (theory, practice away from the computer).
- Percentages, colors and streaks are computed from minutes rounded to the nearest minute,
  so a few seconds never turn a met goal into a missed one.

Stored in ~/.guitarr/plan.json. Category names of the built-in categories are translated
in the UI; custom categories keep the name you typed.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta

from . import config, store
from .errors import CodedError

_lock = threading.Lock()

BUILTIN = ("technique", "repertoire", "theory", "free")
DEFAULT_MINUTES = dict(technique=10, repertoire=15, theory=5, free=0)
AUTO_CATEGORY = dict(exercise="technique", chord="technique", drill="technique", warmup="technique", improv="technique", neck="technique",
                     practice="repertoire")
AUTO_IDS = ("technique", "repertoire", "free")     # counted on their own (free = playing with the tone rig on)
MAX_FREE_CHUNK_S = 120                             # the page reports free play every ~30 s
MAX_GAP_S = 8.0          # a longer silence between notes is a pause, not practice
TAIL_S = 1.5             # the last note rings a little
MAX_MINUTES = 600        # per category and day
HEARTBEAT_S = 60.0       # a running timer nobody has seen for this long is paused
MAX_NAME = 40


class PlanError(CodedError):
    pass


# ---------------------------------------------------------------- storage
def path():
    return store.path("plan")


def _empty() -> dict:
    cats = [dict(id=c, name=None, default_min=DEFAULT_MINUTES[c], active=True) for c in BUILTIN]
    return dict(categories=cats, weeks={}, days={}, timer=None, since=None, day_goals={})


def _read() -> dict:
    d = store.read("plan")
    base = _empty()
    d = {**base, **(d if isinstance(d, dict) else {})}
    if not any(c["id"] == "free" for c in d["categories"]):     # added after the first version
        d["categories"].append(dict(id="free", name=None, default_min=0, active=True))
    if not d["since"]:              # the first day the plan existed: earlier days have no data
        known = sorted(d["days"])
        d["since"] = known[0] if known else date.today().isoformat()
    return d


def _write(d: dict) -> None:
    store.write("plan", d)


# ---------------------------------------------------------------- helpers
def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def active_seconds(times: list[float], max_gap: float = MAX_GAP_S, tail: float = TAIL_S) -> float:
    """Playing time from note times: gaps up to `max_gap` count, longer ones are pauses."""
    if not times:
        return 0.0
    ts = sorted(times)
    total = sum(min(b - a, max_gap) for a, b in zip(ts, ts[1:]))
    return round(total + tail, 2)


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.strip().lower())
    return re.sub(r"\s+", " ", "".join(ch for ch in s if not unicodedata.combining(ch)))


def _cat(d: dict, cid: str) -> dict:
    c = next((c for c in d["categories"] if c["id"] == cid), None)
    if c is None:
        raise PlanError("no_category", "No such category")
    return c


def _minutes(v) -> int:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise PlanError("bad_minutes", "Minutes must be a whole number") from None
    if f != int(f):
        raise PlanError("bad_minutes", "Minutes must be a whole number")
    m = int(f)
    if m < 0:
        raise PlanError("negative_minutes", "Time can't be negative")
    if m > MAX_MINUTES:
        raise PlanError("too_many_minutes", f"At most {MAX_MINUTES} minutes a day per category")
    return m


def _week(d: dict, day: date) -> dict:
    """The week of `day`, created from the latest earlier week (or the defaults) if missing."""
    key = week_start(day).isoformat()
    w = d["weeks"].get(key)
    if w is None:
        active = [c for c in d["categories"] if c["active"]]
        earlier = sorted(k for k in d["weeks"] if k < key)
        last = d["weeks"][earlier[-1]]["minutes"] if earlier else {}
        w = d["weeks"][key] = dict(minutes={c["id"]: last.get(c["id"], c["default_min"]) for c in active})
    return w


def _daily_goal(d: dict, day: date) -> int | None:
    frozen = d.get("day_goals", {}).get(day.isoformat())
    if frozen is not None:
        return frozen
    w = d["weeks"].get(week_start(day).isoformat())
    return None if w is None else sum(w["minutes"].values())


def _freeze_past(d: dict, today: date) -> None:
    """Before the plan changes, the days of this week that are over keep their goal."""
    w = _week(d, today)
    goal = sum(w["minutes"].values())
    frozen = d.setdefault("day_goals", {})
    day = week_start(today)
    while day < today:
        frozen.setdefault(day.isoformat(), goal)
        day += timedelta(days=1)


def _log(d: dict, day: date, cid: str, seconds: float) -> None:
    if seconds <= 0:
        return
    rec = d["days"].setdefault(day.isoformat(), {})
    rec[cid] = round(rec.get(cid, 0.0) + seconds, 2)


def _day_seconds(d: dict, day: date) -> dict:
    return dict(d["days"].get(day.isoformat(), {}))


# ---------------------------------------------------------------- timer
def _midnight_after(day: date) -> float:
    return datetime.combine(day + timedelta(days=1), datetime.min.time()).timestamp()


def _settle(d: dict, now: float) -> None:
    """Applies the timer rules: a timer nobody has seen for a while is paused at the last time
    it was seen, and a timer that crosses midnight is saved on its own day and released."""
    tm = d.get("timer")
    if not tm or tm.get("started") is None:
        return
    seen = tm.get("seen", tm["started"])
    end = now if now - seen <= HEARTBEAT_S else seen
    day = date.fromisoformat(tm["day"])
    midnight = _midnight_after(day)
    if end >= midnight:
        _log(d, day, tm["category"], midnight - tm["started"])
        d["timer"] = None
        return
    if end < now:                          # the page was closed: pause where it was last seen
        _log(d, day, tm["category"], end - tm["started"])
        tm["started"] = None


def timer(action: str, category: str | None = None, now: float | None = None) -> dict:
    """action: start | pause | resume | stop | beat (the page is still open)."""
    now = time.time() if now is None else now
    with _lock:
        d = _read()
        _settle(d, now)
        tm = d.get("timer")
        today = date.fromtimestamp(now)
        if action == "start":
            if tm:
                raise PlanError("timer_busy", "Another timer is already running or paused")
            c = _cat(d, category or "")
            if not c["active"]:
                raise PlanError("no_category", "No such category")
            d["timer"] = dict(category=c["id"], day=today.isoformat(), started=now, seen=now)
        elif tm is None:
            if action != "beat":
                raise PlanError("no_timer", "No timer")
        elif action == "pause":
            if tm["started"] is not None:
                _log(d, date.fromisoformat(tm["day"]), tm["category"], now - tm["started"])
                tm["started"] = None
        elif action == "resume":
            if tm["started"] is None:
                if tm["day"] != today.isoformat():
                    tm["day"] = today.isoformat()
                tm["started"] = tm["seen"] = now
        elif action == "stop":
            if tm["started"] is not None:
                _log(d, date.fromisoformat(tm["day"]), tm["category"], now - tm["started"])
            d["timer"] = None
        elif action == "beat":
            if tm["started"] is not None:
                tm["seen"] = now
        else:
            raise PlanError("bad_action", "Unknown timer action")
        _write(d)
        return view(d, now)


def pause_timer(now: float | None = None) -> None:
    """A listening session starts: pause the manual timer so time isn't counted twice."""
    with _lock:
        d = _read()
        tm = d.get("timer")
        if tm and tm.get("started") is not None:
            now = time.time() if now is None else now
            _settle(d, now)
            tm = d.get("timer")
            if tm and tm["started"] is not None:
                _log(d, date.fromisoformat(tm["day"]), tm["category"], now - tm["started"])
                tm["started"] = None
            _write(d)


# ---------------------------------------------------------------- automatic tracking
def record_session(ctx: dict | None, report: dict, day: date | None = None) -> float:
    """Adds the playing time of a listening session to its category. Returns the seconds."""
    if report.get("simulated"):
        return 0.0
    secs = float(report.get("summary", {}).get("played_s") or 0)
    if secs <= 0:
        return 0.0
    cid = AUTO_CATEGORY.get((ctx or {}).get("type") or "practice", "repertoire")
    with _lock:
        d = _read()
        _log(d, day or date.today(), cid, secs)
        _write(d)
    return secs


def record_free_play(seconds, day: date | None = None) -> float:
    """Playing time reported by the tone rig (real input, signal above the noise floor)."""
    try:
        secs = float(seconds)
    except (TypeError, ValueError):
        raise PlanError("bad_seconds", "Seconds must be a number") from None
    secs = max(0.0, min(secs, MAX_FREE_CHUNK_S))
    if secs:
        with _lock:
            d = _read()
            if any(c["id"] == "free" and c["active"] for c in d["categories"]):
                _log(d, day or date.today(), "free", secs)
                _write(d)
            else:
                secs = 0.0
    return secs


# ---------------------------------------------------------------- editing the plan
def set_minutes(cid: str, minutes) -> dict:
    m = _minutes(minutes)
    with _lock:
        d = _read()
        c = _cat(d, cid)
        if not c["active"]:
            raise PlanError("no_category", "No such category")
        _freeze_past(d, date.today())
        w = _week(d, date.today())
        if m == 0 and sum(v for k, v in w["minutes"].items() if k != cid) == 0:
            raise PlanError("zero_goal", "The plan needs at least one minute a day")
        w["minutes"][cid] = m
        _write(d)
        return view(d)


def set_weekly_goal(total_minutes) -> dict:
    """Scales the current week's categories to a new weekly goal, keeping their proportions.
    The daily goal is the weekly goal ÷ 7, rounded up; rounding leftovers go to the largest
    category (the first one on a tie)."""
    total = _minutes_total(total_minutes)
    daily = math.ceil(total / 7)
    with _lock:
        d = _read()
        _freeze_past(d, date.today())
        w = _week(d, date.today())
        ids = list(w["minutes"])
        if not ids:
            raise PlanError("no_category", "Add a category first")
        cur = [w["minutes"][k] for k in ids]
        base = sum(cur)
        shares = [daily * v / base for v in cur] if base else [daily / len(ids)] * len(ids)
        new = [math.floor(s) for s in shares]
        biggest = max(range(len(ids)), key=lambda i: (shares[i], -i))
        new[biggest] += daily - sum(new)
        w["minutes"] = dict(zip(ids, new))
        _write(d)
        return view(d)


def _minutes_total(v) -> int:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise PlanError("bad_minutes", "Minutes must be a whole number") from None
    if f != int(f):
        raise PlanError("bad_minutes", "Minutes must be a whole number")
    if f < 0:
        raise PlanError("negative_minutes", "Time can't be negative")
    if f == 0:
        raise PlanError("zero_goal", "The goal must be more than 0")
    if f > MAX_MINUTES * 7:
        raise PlanError("too_many_minutes", "That goal is too big")
    return int(f)


def add_category(name: str, minutes) -> dict:
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name:
        raise PlanError("empty_name", "The category needs a name")
    if len(name) > MAX_NAME:
        raise PlanError("long_name", f"At most {MAX_NAME} characters")
    m = _minutes(minutes)
    with _lock:
        d = _read()
        key = _norm(name)
        same = next((c for c in d["categories"] if c["name"] and _norm(c["name"]) == key), None)
        if same and same["active"]:
            raise PlanError("duplicate_name", "There's already a category with that name")
        if same:                            # it existed before: bring it back with its history
            same.update(active=True, default_min=m)
            c = same
        else:
            c = dict(id="c" + uuid.uuid4().hex[:8], name=name, default_min=m, active=True)
            d["categories"].append(c)
        _freeze_past(d, date.today())
        _week(d, date.today())["minutes"][c["id"]] = m
        _write(d)
        return view(d)


def remove_category(cid: str) -> dict:
    """Removes a category from the plan. Its practiced time is kept."""
    with _lock:
        d = _read()
        c = _cat(d, cid)
        active = [x for x in d["categories"] if x["active"]]
        if c["active"] and len(active) == 1:
            raise PlanError("last_category", "Keep at least one category")
        if d.get("timer") and d["timer"]["category"] == cid:
            raise PlanError("timer_busy", "Stop its timer first")
        _freeze_past(d, date.today())
        w = _week(d, date.today())
        rest = sum(v for k, v in w["minutes"].items() if k != cid)
        if rest == 0:
            raise PlanError("zero_goal", "The plan needs at least one minute a day")
        c["active"] = False
        w["minutes"].pop(cid, None)
        _write(d)
        return view(d)


# ---------------------------------------------------------------- the view
def _status(minutes: int, goal: int | None) -> str | None:
    if not goal:
        return None
    pct = 100 * minutes / goal
    return "met" if pct >= 100 else "half" if pct >= 50 else "low"


def goal_streak(d: dict, today: date) -> int:
    """Days in a row that reached their daily goal, counting back from yesterday; today
    counts too once its goal is met."""
    def met(day):
        goal = _daily_goal(d, day)
        mins = round(sum(_day_seconds(d, day).values()) / 60)
        return bool(goal) and mins >= goal
    n = 1 if met(today) else 0
    day = today - timedelta(days=1)
    while met(day):
        n += 1
        day -= timedelta(days=1)
    return n


def view(d: dict | None = None, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    if d is None:
        with _lock:
            d = _read()
            before = json.dumps(d, sort_keys=True)
            _settle(d, now)
            _week(d, date.fromtimestamp(now))
            if json.dumps(d, sort_keys=True) != before:
                _write(d)
    today = date.fromtimestamp(now)
    w = _week(d, today)
    start = week_start(today)
    goal = sum(w["minutes"].values())
    tm = d.get("timer")
    live = 0.0
    if tm and tm.get("started") is not None:
        live = max(0.0, now - tm["started"])

    def seconds_of(day):
        s = _day_seconds(d, day)
        if tm and live and tm["day"] == day.isoformat():
            s[tm["category"]] = s.get(tm["category"], 0.0) + live
        return s

    days = []
    for i in range(7):
        day = start + timedelta(days=i)
        mins = round(sum(seconds_of(day).values()) / 60)
        state = "future" if day > today else "today" if day == today else "past"
        if state == "past" and day.isoformat() < d["since"] and not seconds_of(day):
            state = "before"                     # before you started using the plan
        blank = state in ("future", "before")
        dgoal = d.get("day_goals", {}).get(day.isoformat(), goal) if state == "past" else goal
        days.append(dict(date=day.isoformat(), minutes=None if blank else mins, goal=dgoal,
                         state=state, status=None if blank else _status(mins, dgoal)))
    week_min = sum(x["minutes"] or 0 for x in days)
    finished = [x for x in days if x["state"] == "past"]
    estimate = _status(sum(x["minutes"] for x in finished), sum(x["goal"] for x in finished)) if finished else None
    prev_start = start - timedelta(days=7)
    prev_days = [prev_start + timedelta(days=i) for i in range(7)]
    has_prev = prev_start.isoformat() in d["weeks"] or any(x.isoformat() in d["days"] for x in prev_days)
    prev_min = sum(round(sum(_day_seconds(d, x).values()) / 60) for x in prev_days) if has_prev else None
    today_s = seconds_of(today)
    today_min = round(sum(today_s.values()) / 60)
    cats = []
    for c in d["categories"]:
        if not c["active"]:
            continue
        cats.append(dict(id=c["id"], name=c["name"], builtin=c["id"] in BUILTIN, default_min=c["default_min"],
                         minutes=w["minutes"].get(c["id"], 0), auto=c["id"] in AUTO_IDS,
                         today_s=round(today_s.get(c["id"], 0.0), 1)))
    timer_view = None
    if tm:
        timer_view = dict(category=tm["category"], running=tm.get("started") is not None,
                          elapsed=round(live, 1), day=tm["day"])
    return dict(
        today=dict(date=today.isoformat(), minutes=today_min, goal=goal, remaining=max(0, goal - today_min),
                   status=_status(today_min, goal)),
        week=dict(start=start.isoformat(), end=(start + timedelta(days=6)).isoformat(), minutes=week_min,
                  goal=goal * 7, estimate=estimate, previous=prev_min, days=days),
        streak=goal_streak(d, today), categories=cats, timer=timer_view,
    )


def get() -> dict:
    return view()


def get_days() -> dict:
    """{day: {category: seconds}} for every day with practice (for the consistency map)."""
    with _lock:
        return {k: dict(v) for k, v in _read()["days"].items()}
