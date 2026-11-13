"""Session history (one JSON per session) and problem bars.

The local app keeps a folder per song in config.HISTORY_DIR; the web service keeps rows of
`practice_sessions` (a user's folders from before the database are moved in on first use)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import config, db, store


def song_id(ref_path: str, track: str | None = None) -> str:
    base = Path(ref_path).stem + (f"--{track}" if track else "")
    return re.sub(r"[^\w\-]+", "_", base).strip("_").lower() or "song"


def save(result: dict, section: dict | None = None) -> Path | int:
    ref = result.get("reference", {})
    sid = song_id(ref.get("path", "song"), ref.get("track"))
    data = dict(result)
    data.pop("roll", None)  # the piano roll is heavy and can be regenerated
    data.setdefault("date", datetime.now().isoformat(timespec="seconds"))
    data["song_id"] = sid
    if section:
        data["section"] = section
    if store.in_db():
        _import_folders()
        with db.pool().connection() as conn:
            return _insert(conn, sid, data)
    folder = config.HISTORY_DIR / sid
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = folder / f"{stamp}-{data.get('kind', 'live')}.json"
    config.write_json(path, data)
    return path


def _insert(conn, sid: str, data: dict) -> int:
    from psycopg.types.json import Jsonb
    return conn.execute("INSERT INTO practice_sessions (user_id, song_id, kind, played_at, data) "
                        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (config.user_id(), sid, data.get("kind") or "live", data["date"], Jsonb(data))).fetchone()["id"]


def _import_folders() -> None:
    """Moves the user's history folders (kept as files before the database) into the database, once."""
    root = config.HISTORY_DIR
    if not root.is_dir():
        return
    with db.pool().connection() as conn:
        for p in sorted(root.glob("*/*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            d.setdefault("date", datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"))
            _insert(conn, p.parent.name, d)
    root.rename(root.with_name(root.name + ".imported"))


def export():
    """Every session, for a backup: (song id, file name, data)."""
    if store.in_db():
        _import_folders()
        with db.pool().connection() as conn:
            rows = conn.execute("SELECT id, song_id, kind, data FROM practice_sessions WHERE user_id = %s ORDER BY id",
                                (config.user_id(),)).fetchall()
        for r in rows:
            yield r["song_id"], f"{r['id']:010d}-{r['kind']}.json", r["data"]
        return
    if config.HISTORY_DIR.is_dir():
        for p in sorted(config.HISTORY_DIR.glob("*/*.json")):
            try:
                yield p.parent.name, p.name, json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue


def restore_session(sid: str, name: str, data: dict) -> None:
    """A session from a backup; one that's already there (same song, time and kind) is skipped."""
    if not store.in_db():
        config.write_json(config.HISTORY_DIR / sid / name, data)
        return
    data.setdefault("date", datetime.now().isoformat(timespec="seconds"))
    with db.pool().connection() as conn:
        if not conn.execute("SELECT 1 FROM practice_sessions WHERE user_id = %s AND song_id = %s AND played_at = %s "
                            "AND kind = %s", (config.user_id(), sid, data["date"], data.get("kind") or "live")).fetchone():
            _insert(conn, sid, data)


def load_sessions(sid: str) -> list[dict]:
    if store.in_db():
        _import_folders()
        with db.pool().connection() as conn:
            rows = conn.execute("SELECT id, data FROM practice_sessions WHERE user_id = %s AND song_id = %s "
                                "ORDER BY played_at, id", (config.user_id(), sid)).fetchall()
        return [dict(r["data"], file=str(r["id"])) for r in rows]
    folder = config.HISTORY_DIR / sid
    out = []
    for p in sorted(folder.glob("*.json")):
        try:
            d = json.loads(p.read_text())
            d["file"] = p.name
            out.append(d)
        except (OSError, json.JSONDecodeError):
            continue
    return out


def songs() -> list[dict]:
    out = []
    for sid, n, last in _last_sessions():
        out.append(dict(id=sid, name=last.get("reference", {}).get("name", sid),
                        path=last.get("reference", {}).get("path"), track=last.get("reference", {}).get("track"),
                        sessions=n, last_date=last.get("date"),
                        last_score=session_score(last)))
    out.sort(key=lambda s: s["last_date"] or "", reverse=True)
    return out


def _last_sessions():
    """(song id, number of sessions, the last one) for every song played."""
    if store.in_db():
        _import_folders()
        with db.pool().connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (song_id) song_id, count(*) OVER (PARTITION BY song_id) AS n, data "
                "FROM practice_sessions WHERE user_id = %s ORDER BY song_id, played_at DESC, id DESC",
                (config.user_id(),)).fetchall()
        return [(r["song_id"], r["n"], r["data"]) for r in rows]
    if not config.HISTORY_DIR.exists():
        return []
    out = []
    for folder in sorted(config.HISTORY_DIR.iterdir()):
        sessions = load_sessions(folder.name) if folder.is_dir() else []
        if sessions:
            out.append((folder.name, len(sessions), sessions[-1]))
    return out


def session_score(s: dict) -> float | None:
    sm = s.get("summary", {})
    return sm.get("score") if sm.get("score") is not None else sm.get("first_try_pct", sm.get("correct_pct"))


def problem_bars(sessions: list[dict], last_n: int = 10, top: int = 3) -> list[dict]:
    """Bars with the most mistakes (relative to their notes) in the latest sessions;
    recent sessions weigh more."""
    agg: dict[int, dict] = {}
    recent = sessions[-last_n:]
    for k, s in enumerate(recent):
        w = 0.5 + 0.5 * (k + 1) / len(recent)
        for b in s.get("bars", []):
            d = agg.setdefault(b["bar"], dict(bar=b["bar"], notes=0.0, errors=0.0, timing=0.0))
            d["notes"] += w * b.get("notes", 0)
            d["errors"] += w * b.get("errors", 0)
            d["timing"] += w * b.get("timing", 0)
    rows = []
    for d in agg.values():
        if d["notes"] <= 0:
            continue
        rate = min(1.0, (d["errors"] + 0.5 * d["timing"]) / d["notes"])
        if rate > 0:
            rows.append(dict(bar=d["bar"], rate=round(rate, 3), errors=round(d["errors"], 1),
                             timing=round(d["timing"], 1)))
    rows.sort(key=lambda r: -r["rate"])
    return rows[:top]


def suggest_command(sid: str, sessions: list[dict]) -> str | None:
    bars = problem_bars(sessions)
    if not bars or not sessions:
        return None
    ref = sessions[-1].get("reference", {})
    b = min(r["bar"] for r in bars[:2]), max(r["bar"] for r in bars[:2])
    path = ref.get("path") or ""
    source = f"--chart {path.split(':', 1)[1]}" if path.startswith("chart:") else path
    track = f" --track {ref['track']!r}" if ref.get("track") else ""
    return (f"guitarr live {source}{track} --start-bar {b[0]} --end-bar {b[1]} "
            f"--mode tempo --speed 0.7 --trainer")


def print_history(sid: str | None = None) -> None:
    if sid is None:
        rows = songs()
        if not rows:
            print("No saved sessions yet.")
            return
        print("Practiced songs:\n")
        for r in rows:
            sc = "—" if r["last_score"] is None else f"{r['last_score']:.0f}%"
            print(f"  {r['id']:30s} {r['sessions']:3d} sessions   last {r['last_date']}  ({sc})")
        print("\nDetails: guitarr history <id>")
        return
    sessions = load_sessions(sid)
    if not sessions:
        print(f"No sessions for '{sid}'. See the list with: guitarr history")
        return
    print(f"History of {sid} ({len(sessions)} sessions):\n")
    for s in sessions[-15:]:
        sc = session_score(s)
        sp = s.get("final_speed") or s.get("speed")
        extra = f"  speed {sp:.0%}" if isinstance(sp, (int, float)) else ""
        sec = s.get("section") or {}
        rng = f"  bars {sec.get('start_bar') or 1}-{sec.get('end_bar') or 'end'}" if sec else ""
        bar = "█" * int((sc or 0) / 5)
        print(f"  {s.get('date', '')[:16]}  {s.get('kind', ''):4s} {bar:20s} "
              f"{'—' if sc is None else f'{sc:.0f}%':>5s}{extra}{rng}")
    pb = problem_bars(sessions)
    if pb:
        print("\nWeakest bars:")
        for r in pb:
            print(f"  bar {r['bar']:3d}  {100 * r['rate']:.0f}% mistakes")
        cmd = suggest_command(sid, sessions)
        if cmd:
            print(f"\nTo practice them:\n  {cmd}")
