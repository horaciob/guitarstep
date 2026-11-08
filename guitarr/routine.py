"""Today's practice: a routine built from your own data, sized to your daily goal.

Steps, in order: tune up, reviews that are due (spaced repetition), the next lesson, your
weakest bars, a chord chart and a chord-change minute. Each step knows how to tell that you
did it today (from progress, history and the practice plan), except tuning, which you tick.
Titles are built in the UI from `kind` + `params`, so they can be translated.
"""
from __future__ import annotations

from datetime import date, datetime

from . import catalog, history, plan, progress

TUNE_MIN = 2
REVIEW_MIN = 3
BARS_MIN = 5
CHART_MIN = 8
DRILL_MIN = 2
MAX_REVIEWS = 3


def _seed_reviews(d: dict, today: date) -> bool:
    """Things passed before spaced review existed get a review schedule (once)."""
    changed = False
    for cid, rec in d["chords"].items():
        key = f"chord:{cid}"
        if key not in d["reviews"] and rec:
            first = min(rec.values())
            d["reviews"][key] = dict(step=0, due=first, last=first)
            changed = True
    for lesson in catalog.lessons():
        for ex in lesson["exercises"]:
            key = f"{lesson['id']}/{ex['id']}"
            score = d["exercises"].get(key)
            if score is not None and score >= ex.get("min", 80) and f"exercise:{key}" not in d["reviews"]:
                d["reviews"][f"exercise:{key}"] = dict(step=0, due=today.isoformat(), last=None)
                changed = True
    return changed


def _played_today(sid: str, today: str) -> bool:
    return any((s.get("date") or "").startswith(today) for s in history.load_sessions(sid)[-20:])


def _events_today(d: dict, today: str) -> list[dict]:
    return [e for e in d["events"] if (e.get("at") or "").startswith(today)]


def build(today: date | None = None) -> dict:
    today = today or date.today()
    t = today.isoformat()
    with progress._lock:
        d = progress._read()
        if _seed_reviews(d, today):
            progress._write(d)
    checked = set(d["checked"].get(t, []))
    events = _events_today(d, t)
    lessons = catalog.lessons()
    steps: list[dict] = []

    def add(sid, kind, minutes, route, done, category, **params):
        steps.append(dict(id=sid, kind=kind, minutes=minutes, route=route, done=bool(done),
                          category=category, params=params))

    add("tune", "tune", TUNE_MIN, "#/tuner", "tune" in checked, "technique")

    # due reviews, plus the ones you already did today (so they stay on the list, ticked)
    due = [k for k, _ in progress.due_reviews(d, today)]
    did = [k for k, r in d["reviews"].items() if r.get("last") == t and k not in due]
    for key in (did + due)[:MAX_REVIEWS]:
        r = d["reviews"][key]
        kind, ref = key.split(":", 1)
        done = r.get("last") == t
        if kind == "chord":
            add(key, "review_chord", REVIEW_MIN, f"#/chords?chord={ref}", done, "technique", chord=ref)
        elif "/" in ref:
            lid, eid = ref.split("/", 1)
            if any(x["id"] == lid for x in lessons):
                ls = next(x for x in lessons if x["id"] == lid)
                ex = next((e for e in ls["exercises"] if e["id"] == eid), {})
                add(key, "review_exercise", REVIEW_MIN, f"#/lesson/{lid}?ex={eid}", done, "technique", lesson=lid, exercise=eid,
                    title=ex.get("title", eid))

    nxt = next((x for x in lessons if x["id"] not in d["lessons"]), None)
    done_lesson = next((e["params"]["lesson"] for e in events if e["code"] in ("exercise_passed", "lesson_completed")), None)
    if nxt or done_lesson:
        lid = done_lesson or nxt["id"]
        ls = next(x for x in lessons if x["id"] == lid)
        add(f"lesson:{lid}", "lesson", ls.get("minutes", 10), f"#/lesson/{lid}", bool(done_lesson), "technique",
            lesson=lid, title=ls["title"])

    for song in history.songs()[:5]:                       # weakest bars of a recent song
        sessions = history.load_sessions(song["id"])
        bars = history.problem_bars(sessions)
        path = song.get("path") or ""
        if not bars or not path:
            continue
        a, z = min(b["bar"] for b in bars[:2]), max(b["bar"] for b in bars[:2])
        if path.startswith("chart:"):
            route = f"#/practice?chart={path[6:]}&from={a}&to={z}"
        else:
            name = path.rsplit("/", 1)[-1]
            route = f"#/practice?song={name}&from={a}&to={z}"
        add(f"bars:{song['id']}", "bars", BARS_MIN, route, _played_today(song["id"], t), "repertoire",
            name=song["name"], start=a, end=z)
        break

    charts = [c for c in catalog.charts() if not c.get("error") and not c.get("mine")]
    if charts:
        lesson_level = next((lvl["number"] for lvl in catalog.course()["levels"]
                             for x in lvl["lessons"] if nxt and x["id"] == nxt["id"]), 99)
        fit = [c for c in charts if (c.get("level") or 1) <= lesson_level] or charts[:1]
        played = {c["id"]: history.load_sessions(history.song_id(f"chart:{c['id']}")) for c in fit}
        today_chart = next((c for c in fit if _played_today(history.song_id(f"chart:{c['id']}"), t)), None)
        last = lambda c: (played[c["id"]][-1].get("date") or "") if played[c["id"]] else ""
        pick = today_chart or min(fit, key=lambda c: (last(c), c.get("level") or 0))
        add(f"chart:{pick['id']}", "chart", CHART_MIN, f"#/practice?chart={pick['id']}", today_chart is not None,
            "repertoire", chart=pick["id"], title=pick["title"])

    lesson_chords = (nxt or {}).get("chords") or []
    if len(lesson_chords) >= 2:
        pair = lesson_chords[:2]
    elif d["drills"]:
        pair = min(d["drills"].items(), key=lambda kv: kv[1])[0].split("-")
    else:
        pair = ["Em", "Am"]
    pk = "-".join(pair)
    add(f"drill:{pk}", "drill", DRILL_MIN, f"#/tools?tab=drill&pair={pk}", d["drill_days"].get(pk) == t,
        "technique", chords=pair)

    goal = plan.get()["today"]["goal"]
    total = sum(s["minutes"] for s in steps)
    return dict(date=t, goal=goal, minutes=total, done=sum(s["done"] for s in steps), steps=steps,
                generated=datetime.now().isoformat(timespec="seconds"))
