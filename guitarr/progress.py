"""Progress: XP, levels, day streak, passed exercises and lessons, mastered chords
(by ear or camera), chord-change records and pinned tutorials.

Everything is decided on the server from what the listener heard, and stored in
~/.guitarr/progress.json (shared by the web UI and the terminal). Events are stored
as `code` + `params` so the UI can show them in any language.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import store

_lock = store.Lock("progress")   # one read-modify-write at a time (across processes as a web service)

LEVELS = [(0, "First strings"), (150, "Accompanist"), (400, "Strummer"), (800, "Blues player"),
          (1500, "Guitarist")]
XP = dict(exercise=15, lesson=40, chord=20, variation=10)
EVENT_TEXT = {
    "practice": "Practice: {name} {score:.0f}%",
    "take_analysis": "Take analysis: {score:.0f}%",
    "exercise_passed": "Exercise passed: {lesson}/{exercise}",
    "lesson_completed": "Lesson completed: {lesson}",
    "chord_mastered": "Chord {chord} mastered ({via})",
    "drill": "Chord-change minute {chords}: {changes} changes",
    "lesson_tested_out": "Lesson tested out: {lesson}",
    "rhythm": "Rhythm test at {bpm} BPM: {within}% on time",
    "ear": "Ear training ({kind}): {score:.0f}%",
    "variation_passed": "Variation passed: {lesson}/{exercise}",
    "warmup": "Warm-up {drill} at {bpm} BPM: {score:.0f}%",
    "improv": "Improvised over {backing}: {score:.0f}",
    "neck": "Neck game: {found} notes in {seconds} s",
    "challenge": "Weekly challenge done: {id}",
}


def _empty() -> dict:
    return dict(xp=0, days=[], lessons=[], exercises={}, chords={}, drills={}, tutorials={}, events=[],
                reviews={}, drill_days={}, checked={},
                guidance={},      # exercise → the least help you passed it with (0 full, 1 names only, 2 none)
                variations={},    # exercise → best score in another key or position
                hints={},         # exercise → hints you used in your last attempt
                sections={},      # chart → {section: {state, bpm}}
                seen=[],          # lessons you've opened (the "discover" step)
                tested_out=[],    # lessons you skipped by passing their check
                rhythm={},        # rhythm test → best (steadiest) result per tempo
                ear={},           # ear trainer → best score per kind
                warmup={},        # daily warm-up → {drill: {bpm (the goal), best, day}}
                improv={},        # improvising → {backing: {best, last, day}}
                neck={},          # neck game → {strings+accidentals-seconds: {best, last, day}}
                start_level=None,  # where the placement says to start the course (a level id)
                weekly={},        # this week's challenges → {week: {counts: {award code: n}, done: [ids]}}
                facts={},         # weak spots: facts you missed → {label, lesson, exercise, misses, step, due}
                budget=None,      # minutes you chose for today's plan (15, 30, 60, 120)
                queue=[])         # song or chart sections you pinned to today's plan


# rhythm test: how early (−) or late (+) each strum was, in bins with the count in each
RHYTHM_EDGES = (-100, -60, -30, -10, 10, 30, 60, 100)


def rhythm_stats(ms: list[int]) -> dict:
    """{n, mean, std, within (% inside ±30 ms), bins: [{lo, hi, count}]} from per-strum timing errors."""
    if not ms:
        return dict(n=0, mean=None, std=None, within=None, bins=[])
    edges = [None, *RHYTHM_EDGES, None]
    bins = [dict(lo=a, hi=b, count=sum(1 for x in ms if (a is None or x >= a) and (b is None or x < b)))
            for a, b in zip(edges, edges[1:])]
    n = len(ms)
    mean = sum(ms) / n
    std = (sum((x - mean) ** 2 for x in ms) / n) ** 0.5
    return dict(n=n, mean=round(mean), std=round(std), within=round(100 * sum(abs(x) <= 30 for x in ms) / n), bins=bins)


def ear_result(kind: str, score: float) -> dict:
    """An ear-training round from the tools (not tied to a lesson): best score per kind, a little XP."""
    with _lock:
        d = _read()
        prev = d["ear"].get(kind, {}).get("best")
        d["ear"][kind] = dict(best=max(score, prev or 0), last=score, day=date.today().isoformat())
        out = dict(score=score, best=d["ear"][kind]["best"], record=prev is not None and score > prev, xp=0)
        if score >= 80:
            _award(d, 5, "ear", kind=kind, score=score)
            out["xp"] = 5
        _write(d)
        return out


QUEUE_MAX = 8


def queue_add(ref: str, section: str) -> list[dict]:
    """Pins a song or chart section to today's plan; it stays until you clear it."""
    with _lock:
        d = _read()
        q = d.setdefault("queue", [])
        if not any(x["ref"] == ref and x["section"] == section for x in q):
            if len(q) >= QUEUE_MAX:
                raise ValueError("queue_full")
            q.append(dict(ref=ref, section=section, added=date.today().isoformat()))
        _write(d)
        return q


def queue_remove(ref: str | None = None, section: str | None = None) -> list[dict]:
    """Removes one pinned item (or all of them, with no arguments)."""
    with _lock:
        d = _read()
        d["queue"] = [] if ref is None else [x for x in d.get("queue", []) if not (x["ref"] == ref and x["section"] == section)]
        _write(d)
        return d["queue"]


BUDGETS = (15, 30, 60, 120)


def set_budget(minutes: int | None) -> int | None:
    if minutes is not None and minutes not in BUDGETS:
        raise ValueError("bad_budget")
    with _lock:
        d = _read()
        d["budget"] = minutes
        _write(d)
        return minutes


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


FACT_DAYS = (1, 3, 7)      # a missed fact comes back today; then after 1, 3 and 7 days right; then it's gone
FACTS_MAX = 200


def record_facts(facts: list[dict], today: date | None = None) -> None:
    """Weak spots: a miss puts the fact on today's list (or back to the start); a right answer on a due fact moves it
    1, 3, then 7 days ahead, and after that it's retired. Facts you never missed aren't tracked."""
    if not facts:
        return
    t = (today or date.today())
    with _lock:
        d = _read()
        for f in facts:
            cur = d["facts"].get(f["key"])
            if not f["ok"]:
                d["facts"][f["key"]] = dict(label=f["label"], lesson=f["lesson"], exercise=f["exercise"],
                                            misses=(cur or {}).get("misses", 0) + 1, step=0, due=t.isoformat())
            elif cur and t.isoformat() >= cur["due"]:
                if cur["step"] >= len(FACT_DAYS):
                    d["facts"].pop(f["key"])
                else:
                    cur.update(due=(t + timedelta(days=FACT_DAYS[cur["step"]])).isoformat(), step=cur["step"] + 1)
        if len(d["facts"]) > FACTS_MAX:                  # keep the most missed ones
            keep = sorted(d["facts"].items(), key=lambda kv: -kv[1]["misses"])[:FACTS_MAX]
            d["facts"] = dict(keep)
        _write(d)


def fact_route(f: dict) -> str:
    """Where to practice a weak fact again: its exercise, or the tool it came from."""
    ex = f["exercise"]
    if f["lesson"] != "__tools__":
        return f"#/lesson/{f['lesson']}?ex={ex}"
    if ex.startswith("ear-cycle-"):
        return f"#/tools?tab=ear&ear=cycle&module={ex[len('ear-cycle-'):]}"
    return f"#/tools?tab=ear&ear={ex.removeprefix('ear-')}"


def weak_facts(d: dict | None = None, today: date | None = None, limit: int = 8) -> list[dict]:
    """Facts due today, the most missed first: [{key, label, lesson, exercise, misses}]."""
    d = d or get()
    t = (today or date.today()).isoformat()
    due = [dict(key=k, **v) for k, v in d.get("facts", {}).items() if v["due"] <= t]
    return sorted(due, key=lambda f: (-f["misses"], f["due"]))[:limit]


def due_reviews(d: dict, today: date | None = None) -> list[tuple[str, dict]]:
    t = (today or date.today()).isoformat()
    return sorted(((k, r) for k, r in d["reviews"].items() if r["due"] <= t and not r.get("retired")), key=lambda kr: kr[1]["due"])


def path():
    return store.path("progress")


def _read() -> dict:
    d = store.read("progress")
    return {**_empty(), **(d if isinstance(d, dict) else {})}


def _write(d: dict) -> None:
    store.write("progress", d)


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
    if code != "challenge":                     # this week's challenges: a bonus for each one completed
        from . import weekly
        for cid in weekly.on_award(d, code):
            _award(d, weekly.BONUS_XP, "challenge", id=cid)


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


def _record_exercise(d: dict, lid: str, eid: str, score: float | None, need: float, complete: bool = True,
                     guidance: int = 0, hints: int = 0, variant: bool = False) -> dict:
    """Stores an exercise result (best score, review schedule, XP, lesson completion) → what was earned.
    guidance: how much help was on screen (0 full, 1 names only, 2 none); hints: how many you asked for;
    variant: the exercise in another key or position (scored on its own, it doesn't change the main score)."""
    from . import catalog

    key = f"{lid}/{eid}"
    passed = score is not None and complete and score >= need
    if variant:
        out = dict(xp=0, passed=passed, score=score, need=need, variant=True)
        prev = d["variations"].get(key)
        if score is not None and (prev is None or score > prev):
            d["variations"][key] = score
        if passed and (prev is None or prev < need):
            _award(d, XP["variation"], "variation_passed", lesson=lid, exercise=eid)
            out["xp"] = XP["variation"]
        return out
    d["hints"][key] = hints
    if passed and guidance > d["guidance"].get(key, -1):
        d["guidance"][key] = guidance
    prev = d["exercises"].get(key)
    out: dict = dict(xp=0, passed=passed, score=score, need=need, guidance=guidance, hints=hints)
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


def _test_out(d: dict, lid: str) -> dict:
    """You showed you already know a lesson: every exercise counts as passed and the lesson is complete."""
    from . import catalog

    lesson = catalog.get_lesson(lid)
    for e in lesson["exercises"]:
        key = f"{lid}/{e['id']}"
        if d["exercises"].get(key, -1) < e.get("min", 80):
            d["exercises"][key] = float(e.get("min", 80))
    out = dict(tested_out=True)
    if lid not in d["tested_out"]:
        d["tested_out"].append(lid)
    if lid not in d["lessons"]:
        d["lessons"].append(lid)
        _award(d, XP["lesson"], "lesson_tested_out", lesson=lid)
        out.update(xp=XP["lesson"], lesson_done=True)
    return out


def test_out(lid: str) -> dict:
    """Completes a lesson whose check you passed (used when the check has no part to play)."""
    with _lock:
        d = _read()
        out = _test_out(d, lid)
        _write(d)
        return out


def mark_seen(lid: str) -> None:
    with _lock:
        d = _read()
        if lid not in d["seen"]:
            d["seen"].append(lid)
            _write(d)


SECTION_STATES = ("not_started", "learning", "unsure", "solid", "ready")


def set_section(chart: str, section: str, state: str | None = None, bpm: float | None = None, preset: str | None = None) -> dict:
    """A song section's state (one of SECTION_STATES), target tempo and tone recipe (a rig preset:
    "factory:<id>" or "user:<id>"; "" clears it)."""
    if state is not None and state not in SECTION_STATES:
        raise ValueError("bad_state")
    if bpm is not None and not 20 <= bpm <= 300:
        raise ValueError("bad_bpm")
    with _lock:
        d = _read()
        rec = d["sections"].setdefault(chart, {}).setdefault(section, dict(state="not_started", bpm=None))
        if state is not None:
            rec["state"] = state
        if bpm is not None:
            rec["bpm"] = bpm
        if preset is not None:
            if preset and not preset.startswith(("factory:", "user:")):
                raise ValueError("bad_preset")
            rec["preset"] = preset or None
        _write(d)
        return d["sections"][chart]


def section_mastery(states: list[str]) -> int:
    """0–100: the average of the sections' states (not started 0 … ready 100)."""
    if not states:
        return 0
    return round(sum(SECTION_STATES.index(s) for s in states) / (len(states) * (len(SECTION_STATES) - 1)) * 100)


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
            out.update(_record_exercise(d, ctx["lesson"], ctx["exercise"], score, ctx.get("min", 80), complete,
                                        int(ctx.get("guidance", 0)), int(ctx.get("hints", 0)), bool(ctx.get("variant"))))
            if ctx.get("testout") and out.get("passed"):
                out.update(_test_out(d, ctx["lesson"]))
        elif kind == "rhythm":
            st = rhythm_stats(s.get("timing_ms") or [])
            out["rhythm"] = st
            if st["n"]:
                key = str(int(ctx.get("bpm", 0)))
                best = d["rhythm"].get(key)
                if best is None or st["std"] < best["std"]:
                    d["rhythm"][key] = dict(std=st["std"], within=st["within"], day=date.today().isoformat())
                    out["record"] = best is not None
                _award(d, 5, "rhythm", bpm=ctx.get("bpm"), within=st["within"])
                out["xp"] = 5
        elif kind == "neck":
            found = s.get("first_try", 0) + s.get("fixed", 0)
            prev = d["neck"].get(ctx["key"], {}).get("best")
            if found:
                d["neck"][ctx["key"]] = dict(best=max(found, prev or 0), last=found, day=date.today().isoformat())
                xp = 5 if found >= 10 else 2
                _award(d, xp, "neck", found=found, seconds=ctx["seconds"])
                out["xp"] = xp
            out.update(found=found, first_try=s.get("first_try", 0), best=max(found, prev or 0),
                       record=prev is not None and found > prev)
        elif kind == "improv":
            if score is not None:
                prev = d["improv"].get(ctx["backing"], {}).get("best")
                d["improv"][ctx["backing"]] = dict(best=max(score, prev or 0), last=score, day=date.today().isoformat())
                out.update(score=score, record=prev is not None and score > prev)
                _award(d, 5, "improv", backing=ctx["backing"], score=score)
                out["xp"] = 5
        elif kind == "echo":
            if score is not None:
                prev = d["ear"].get("echo", {}).get("best")
                d["ear"]["echo"] = dict(best=max(score, prev or 0), last=score, day=date.today().isoformat())
                out.update(passed=score >= 75, score=score, need=75)
                if score >= 75:
                    _award(d, 5, "ear", kind="echo", score=score)
                    out["xp"] = 5
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
        elif kind == "warmup":
            from . import warmup
            drill, played = ctx["drill"], float(ctx["bpm"])
            cur = warmup.goal(d["warmup"], drill)
            new = warmup.next_goal(cur, played, score if s.get("judged") else None)
            prev = d["warmup"].get(drill, {})
            d["warmup"][drill] = dict(bpm=new, best=max(score or 0, prev.get("best") or 0), day=date.today().isoformat())
            out.update(score=score, goal=new, raised=new > cur, need=warmup.PASS)
            if score is not None and s.get("judged"):
                xp = 5 if new > cur else 2
                _award(d, xp, "warmup", drill=drill, bpm=round(played), score=score)
                out["xp"] = xp
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
    from .placement import next_lesson
    nxt = next_lesson(set(d["lessons"]), d.get("start_level"))
    if nxt:
        print(f"    next: {nxt['title']}  (guitarr gui → Course)")
    print(f"  mastered chords: {', '.join(sorted(d['chords'])) or '—'}")
    if d["drills"]:
        print("  chord-change minute: " + ", ".join(f"{k.replace('-', '↔')} {v}" for k, v in d["drills"].items()))
    if d["events"]:
        print("  latest:")
        for e in d["events"][:5]:
            print(f"    {event_text(e)}" + (f"  +{e['xp']} XP" if e.get("xp") else ""))


def set_start_level(lid: str | None) -> None:
    with _lock:
        d = _read()
        d["start_level"] = lid
        _write(d)
