"""The last 7 days on one page, to print or save as a PDF (for yourself or a teacher): practice time per day and
category, songs and charts played with the listener, what you earned, and your skills."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import history, plan, progress, skills


def week(today: date | None = None, days: int = 7) -> dict:
    today = today or date.today()
    span = [(today - timedelta(days=days - 1 - k)).isoformat() for k in range(days)]
    first = span[0]
    secs = plan.get_days()
    cats = {c["id"]: c for c in plan.view()["categories"]}
    day_rows = []
    for d in span:
        by = {cid: round(s / 60) for cid, s in secs.get(d, {}).items() if round(s / 60)}
        day_rows.append(dict(date=d, minutes=round(sum(secs.get(d, {}).values()) / 60), categories=by))
    songs = []
    for s in history.songs():
        ss = [x for x in history.load_sessions(s["id"]) if (x.get("date") or "")[:10] >= first]
        if not ss:
            continue
        scores = [history.session_score(x) for x in ss if history.session_score(x) is not None]
        songs.append(dict(name=s["name"], sessions=len(ss), best=max(scores) if scores else None,
                          last=scores[-1] if scores else None, first=scores[0] if scores else None))
    p = progress.get()
    events = [e for e in p["events"] if (e.get("at") or "")[:10] >= first]
    return dict(start=first, end=span[-1], generated=datetime.now().isoformat(timespec="minutes"),
                minutes=sum(r["minutes"] for r in day_rows), active_days=sum(r["minutes"] > 0 for r in day_rows),
                days=day_rows, categories=[dict(id=c["id"], name=c.get("name"), builtin=c.get("builtin", False))
                                           for c in cats.values()],
                songs=sorted(songs, key=lambda x: -x["sessions"]), events=events, events_capped=len(p["events"]) >= 30,
                xp=p["xp"], level=p["level"], streak=p["streak"], lessons=len(p["lessons"]), skills=skills.compute(p))
