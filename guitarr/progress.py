"""Progress: XP, levels, day streak, passed exercises and lessons, mastered chords
(by ear or camera), chord-change records and pinned tutorials.

Everything is decided on the server from what the listener heard, and stored in
~/.guitarr/progress.json (shared by the web UI and the terminal). Events are stored
as `code` + `params` so the UI can show them in any language.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta

from . import config

_lock = threading.Lock()

LEVELS = [(0, "First strings"), (150, "Accompanist"), (400, "Strummer"), (800, "Blues player"),
          (1500, "Guitarist")]
XP = dict(exercise=15, lesson=40, chord=20)
EVENT_TEXT = {
    "practice": "Practice: {name} {score:.0f}%",
    "take_analysis": "Take analysis: {score:.0f}%",
    "exercise_passed": "Exercise passed: {lesson}/{exercise}",
    "lesson_completed": "Lesson completed: {lesson}",
    "chord_mastered": "Chord {chord} mastered ({via})",
    "drill": "Chord-change minute {chords}: {changes} changes",
}


def _empty() -> dict:
    return dict(xp=0, days=[], lessons=[], exercises={}, chords={}, drills={}, tutorials={}, events=[],
                reviews={}, drill_days={}, checked={})


# ---------------------------------------------------------------- spaced review
# What you already passed comes back after 1, 3, 7, 14, 30 and 60 days. Passing a review moves
# it to the next interval; failing it brings it back tomorrow. Passing the 60-day review retires
# it: it's yours, and it stops coming back (failing it later starts it over).
REVIEW_DAYS = (1, 3, 7, 14, 30, 60)


def _review(d: dict, key: str, ok: bool, today: date | None = None) -> None:
    today = today or date.today()
    r = d["reviews"].get(key)
    if r is None:
        if ok:
            d["reviews"][key] = dict(step=0, due=(today + timedelta(days=REVIEW_DAYS[0])).isoformat(),
                                     last=today.isoformat())
        return
    if ok:
        if r.get("retired"):
            pass
        elif today.isoformat() >= r["due"] and r["step"] == len(REVIEW_DAYS) - 1:
            r["retired"] = True
        elif today.isoformat() >= r["due"]:          # reviewing early doesn't skip ahead
            r["step"] += 1
            r["due"] = (today + timedelta(days=REVIEW_DAYS[r["step"]])).isoformat()
    else:
        r.pop("retired", None)
        r["step"] = 0
        r["due"] = (today + timedelta(days=REVIEW_DAYS[0])).isoformat()
    r["last"] = today.isoformat()


def due_reviews(d: dict, today: date | None = None) -> list[tuple[str, dict]]:
    t = (today or date.today()).isoformat()
    return sorted(((k, r) for k, r in d["reviews"].items() if r["due"] <= t and not r.get("retired")), key=lambda kr: kr[1]["due"])


def path():
    return config.HOME / "progress.json"


def _read() -> dict:
    try:
        d = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    return {**_empty(), **d}


def _write(d: dict) -> None:
    config.HOME.mkdir(parents=True, exist_ok=True)
    tmp = path().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path())


def streak(days: list[str], today: date | None = None) -> int:
    """Consecutive practice days up to today (or up to yesterday if not yet today)."""
    today = today or date.today()
    have = {date.fromisoformat(d) for d in days}
    day = today if today in have else today - timedelta(days=1)
    n = 0
    while day in have:
        n += 1
        day -= timedelta(days=1)
    return n


def level(xp: int) -> dict:
    idx = max(i for i, (lo, _) in enumerate(LEVELS) if xp >= lo)
    lo, title = LEVELS[idx]
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    prog = 1.0 if nxt is None else (xp - lo) / (nxt - lo)
    return dict(level=idx + 1, title=title, next_xp=nxt, progress=round(prog, 3))


def view(d: dict | None = None) -> dict:
    d = d or _read()
    today = date.today().isoformat()
    return {**d, "streak": streak(d["days"]), "practiced_today": today in d["days"], "level": level(d["xp"])}


def get() -> dict:
    with _lock:
        return view()


def event_text(e: dict) -> str:
    try:
        return EVENT_TEXT[e["code"]].format(**e["params"])
    except (KeyError, ValueError):
        return e.get("code", "")


def _award(d: dict, xp: int, code: str, **params) -> None:
    d["xp"] += xp
    today = date.today().isoformat()
    if today not in d["days"]:
        d["days"].append(today)
    ev = dict(at=datetime.now().isoformat(timespec="seconds"), xp=xp, code=code, params=params)
    d["events"] = ([ev] + d["events"])[:30]


def practice_xp(score: float | None) -> int:
    """XP for a listening practice: up to 20, based on the score."""
    if score is None:
        return 0
    return max(2, round(score / 5))


def add_practice(score: float | None, code: str = "practice", **params) -> int:
    xp = practice_xp(score)
    if xp:
        with _lock:
            d = _read()
            _award(d, xp, code, score=score, **params)
            _write(d)
    return xp


def chord_mastered(cid: str, via: str) -> dict:
    """via = 'ear' | 'camera'. The first time a chord is mastered it earns XP."""
    with _lock:
        d = _read()
        rec = d["chords"].setdefault(cid, {})
        first = not rec
        rec[via] = date.today().isoformat()
        _review(d, f"chord:{cid}", True)
        xp = XP["chord"] if first else 0
        _award(d, xp, "chord_mastered", chord=cid, via=via)
        _write(d)
        return dict(xp=xp, first=first, chord=cid)


def check_step(step: str, done: bool) -> dict:
    """Ticks (or unticks) a step of today's practice that can't be detected, like tuning up."""
    today = date.today().isoformat()
    with _lock:
        d = _read()
        steps = set(d["checked"].get(today, []))
        (steps.add if done else steps.discard)(step)
        d["checked"] = {today: sorted(steps)}           # only today's ticks are kept
        _write(d)
        return d["checked"]


def pin_tutorial(lid: str, url: str | None) -> dict:
    with _lock:
        d = _read()
        if url:
            d["tutorials"][lid] = url
        else:
            d["tutorials"].pop(lid, None)
        _write(d)
        return d["tutorials"]


def _record_exercise(d: dict, lid: str, eid: str, score: float | None, need: float, complete: bool = True) -> dict:
    """Stores an exercise result (best score, review schedule, XP, lesson completion) → what was earned."""
    from . import catalog

    key = f"{lid}/{eid}"
    passed = score is not None and complete and score >= need
    prev = d["exercises"].get(key)
    out: dict = dict(xp=0, passed=passed, score=score, need=need)
    if score is not None and (prev is None or score > prev):
        d["exercises"][key] = score
    if score is not None:
        _review(d, f"exercise:{key}", passed)
    if passed and (prev is None or prev < need):
        _award(d, XP["exercise"], "exercise_passed", lesson=lid, exercise=eid)
        out["xp"] += XP["exercise"]
    lesson = catalog.get_lesson(lid)
    done = all(d["exercises"].get(f"{lid}/{e['id']}", -1) >= e.get("min", 80) for e in lesson["exercises"])
    if done and lid not in d["lessons"]:
        d["lessons"].append(lid)
        _award(d, XP["lesson"], "lesson_completed", lesson=lid)
        out.update(xp=out["xp"] + XP["lesson"], lesson_done=True)
    return out


def exercise_answered(lid: str, eid: str, score: float, need: float) -> dict:
    """Records an exercise you pass by answering (a quiz or picking notes on the neck), not by playing."""
    with _lock:
        d = _read()
        out = _record_exercise(d, lid, eid, score, need)
        _write(d)
        out["progress"] = view(d)
        return out


def on_session(ctx: dict | None, report: dict) -> dict:
    """Records a listening session according to its context and returns what was earned."""
    from . import catalog

    s = report.get("summary", {})
    score = s.get("score")
    kind = (ctx or {}).get("type")
    if report.get("simulated") and kind in (None, "practice"):
        return dict(xp=0, progress=view())
    with _lock:
        d = _read()
        out: dict = dict(xp=0)
        if kind == "exercise":
            complete = s.get("judged") == s.get("events")
            out.update(_record_exercise(d, ctx["lesson"], ctx["exercise"], score, ctx.get("min", 80), complete))
        elif kind == "chord":
            ok = s.get("judged", 0) > 0 and (s.get("first_try", 0) > 0 or s.get("fixed", 0) > 0)
            out["passed"] = ok
            if s.get("judged", 0) > 0:
                _review(d, f"chord:{ctx['chord']}", ok)
            if ok:
                rec = d["chords"].setdefault(ctx["chord"], {})
                first = not rec
                rec["ear"] = date.today().isoformat()
                if first:
                    _award(d, XP["chord"], "chord_mastered", chord=ctx["chord"], via="ear")
                    out.update(xp=XP["chord"], first=True)
        elif kind == "drill":
            pair = "-".join(ctx["chords"])
            changes = max(0, s.get("first_try", 0) + s.get("fixed", 0) - 1)
            best = d["drills"].get(pair, 0)
            out.update(changes=changes, best=max(best, changes), record=changes > best)
            d["drills"][pair] = max(best, changes)
            d["drill_days"][pair] = date.today().isoformat()
            xp = changes // 2
            if xp:
                _award(d, xp, "drill", chords=pair, changes=changes)
                out["xp"] = xp
        else:
            xp = practice_xp(score) if s.get("judged") else 0
            if xp:
                _award(d, xp, "practice", name=report.get("reference", {}).get("name", ""), score=score)
                out["xp"] = xp
        _write(d)
        out["progress"] = view(d)
        return out


def print_progress() -> None:
    from . import catalog

    d = get()
    lv = d["level"]
    bar = "█" * int(lv["progress"] * 20)
    print(f"Level {lv['level']} · {lv['title']}")
    print(f"  {d['xp']} XP  {bar:20s} " + (f"(next level: {lv['next_xp']})" if lv["next_xp"] else ""))
    print(f"  🔥 streak: {d['streak']} {'day' if d['streak'] == 1 else 'days'}"
          + ("" if d["practiced_today"] else "  (no practice yet today)"))
    all_l = catalog.lessons()
    print(f"  lessons: {len([x for x in all_l if x['id'] in d['lessons']])}/{len(all_l)}")
    nxt = next((x for x in all_l if x["id"] not in d["lessons"]), None)
    if nxt:
        print(f"    next: {nxt['title']}  (guitarr gui → Course)")
    print(f"  mastered chords: {', '.join(sorted(d['chords'])) or '—'}")
    if d["drills"]:
        print("  chord-change minute: " + ", ".join(f"{k.replace('-', '↔')} {v}" for k, v in d["drills"].items()))
    if d["events"]:
        print("  latest:")
        for e in d["events"][:5]:
            print(f"    {event_text(e)}" + (f"  +{e['xp']} XP" if e.get("xp") else ""))
