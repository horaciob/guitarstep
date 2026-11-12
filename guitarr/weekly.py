"""This week's challenges: three small goals, the same all week, a different set each week. Completing one is
worth a bonus. Counts come from what you earned this week (see progress._award)."""
from __future__ import annotations

from datetime import date, timedelta

BONUS_XP = 20
# id → (what counts, how many). "days" = days you practiced this week; anything else = awards with that code.
CHALLENGES = {
    "days5":      ("days", 5),
    "exercises5": ("exercise_passed", 5),
    "lesson1":    ("lesson_completed", 1),
    "drill3":     ("drill", 3),
    "improv2":    ("improv", 2),
    "neck3":      ("neck", 3),
    "rhythm2":    ("rhythm", 2),
    "warmup4":    ("warmup", 4),
    "ear3":       ("ear", 3),
    "songs3":     ("practice", 3),
}
PER_WEEK = 3


def week_id(d: date | None = None) -> str:
    y, w, _ = (d or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def week_days(d: date | None = None) -> list[str]:
    d = d or date.today()
    monday = d - timedelta(days=d.weekday())
    return [(monday + timedelta(days=k)).isoformat() for k in range(7)]


def picks(wid: str) -> list[str]:
    """The week's challenges: "days5" always, plus two that rotate with the week number."""
    ids = [k for k in CHALLENGES if k != "days5"]
    n = int(wid.split("W")[1]) + int(wid[:4])
    return ["days5", ids[n % len(ids)], ids[(n + 3) % len(ids)]]


def count(d: dict, code: str, today: date | None = None) -> int:
    if code == "days":
        return len(set(d["days"]) & set(week_days(today)))
    return d.get("weekly", {}).get(week_id(today), {}).get("counts", {}).get(code, 0)


def view(d: dict, today: date | None = None) -> dict:
    wid = week_id(today)
    done = d.get("weekly", {}).get(wid, {}).get("done", [])
    out = []
    for cid in picks(wid):
        code, need = CHALLENGES[cid]
        n = min(count(d, code, today), need)
        out.append(dict(id=cid, n=n, need=need, done=cid in done))
    return dict(week=wid, bonus=BONUS_XP, challenges=out)


def on_award(d: dict, code: str, today: date | None = None) -> list[str]:
    """Counts an award for this week; returns the challenges it just completed (their bonus is the caller's)."""
    wid = week_id(today)
    weekly = d.setdefault("weekly", {})
    for old in [k for k in weekly if k != wid]:                # only this week is kept
        del weekly[old]
    w = weekly.setdefault(wid, dict(counts={}, done=[]))
    w["counts"][code] = w["counts"].get(code, 0) + 1
    new = []
    for cid in picks(wid):
        c, need = CHALLENGES[cid]
        if cid not in w["done"] and count(d, c, today) >= need:
            w["done"].append(cid)
            new.append(cid)
    return new
