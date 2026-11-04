"""Historial de sesiones (JSON por sesión) y compases problemáticos."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import config


def song_id(ref_path: str, track: str | None = None) -> str:
    base = Path(ref_path).stem + (f"--{track}" if track else "")
    return re.sub(r"[^\w\-]+", "_", base).strip("_").lower() or "cancion"


def save(result: dict, section: dict | None = None) -> Path:
    ref = result.get("reference", {})
    sid = song_id(ref.get("path", "cancion"), ref.get("track"))
    folder = config.HISTORY_DIR / sid
    folder.mkdir(parents=True, exist_ok=True)
    data = dict(result)
    data.pop("roll", None)  # el piano-roll es pesado y se puede regenerar
    data.setdefault("date", datetime.now().isoformat(timespec="seconds"))
    data["song_id"] = sid
    if section:
        data["section"] = section
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = folder / f"{stamp}-{data.get('kind', 'live')}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return path


def load_sessions(sid: str) -> list[dict]:
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
    if not config.HISTORY_DIR.exists():
        return out
    for folder in sorted(config.HISTORY_DIR.iterdir()):
        if not folder.is_dir():
            continue
        sessions = load_sessions(folder.name)
        if not sessions:
            continue
        last = sessions[-1]
        out.append(dict(id=folder.name, name=last.get("reference", {}).get("name", folder.name),
                        path=last.get("reference", {}).get("path"), track=last.get("reference", {}).get("track"),
                        sessions=len(sessions), last_date=last.get("date"),
                        last_score=session_score(last)))
    out.sort(key=lambda s: s["last_date"] or "", reverse=True)
    return out


def session_score(s: dict) -> float | None:
    sm = s.get("summary", {})
    return sm.get("score") if sm.get("score") is not None else sm.get("first_try_pct", sm.get("correct_pct"))


def problem_bars(sessions: list[dict], last_n: int = 10, top: int = 3) -> list[dict]:
    """Compases con más errores (proporcionales a sus notas) en las últimas sesiones;
    las sesiones recientes pesan más."""
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
    track = f" --track {ref['track']!r}" if ref.get("track") else ""
    return (f"guitarr live {ref.get('path')}{track} --start-bar {b[0]} --end-bar {b[1]} "
            f"--mode tempo --speed 0.7 --trainer")


def print_history(sid: str | None = None) -> None:
    if sid is None:
        rows = songs()
        if not rows:
            print("Todavía no hay sesiones guardadas.")
            return
        print("Canciones practicadas:\n")
        for r in rows:
            sc = "—" if r["last_score"] is None else f"{r['last_score']:.0f}%"
            print(f"  {r['id']:30s} {r['sessions']:3d} sesiones   última {r['last_date']}  ({sc})")
        print("\nDetalle: guitarr history <id>")
        return
    sessions = load_sessions(sid)
    if not sessions:
        print(f"No hay sesiones para '{sid}'. Mirá la lista con: guitarr history")
        return
    print(f"Historial de {sid} ({len(sessions)} sesiones):\n")
    for s in sessions[-15:]:
        sc = session_score(s)
        sp = s.get("final_speed") or s.get("speed")
        extra = f"  vel {sp:.0%}" if isinstance(sp, (int, float)) else ""
        sec = s.get("section") or {}
        rng = f"  c.{sec.get('start_bar') or 1}-{sec.get('end_bar') or 'fin'}" if sec else ""
        bar = "█" * int((sc or 0) / 5)
        print(f"  {s.get('date', '')[:16]}  {s.get('kind', ''):4s} {bar:20s} "
              f"{'—' if sc is None else f'{sc:.0f}%':>5s}{extra}{rng}")
    pb = problem_bars(sessions)
    if pb:
        print("\nCompases más flojos:")
        for r in pb:
            print(f"  compás {r['bar']:3d}  {100 * r['rate']:.0f}% de error")
        cmd = suggest_command(sid, sessions)
        if cmd:
            print(f"\nPara practicarlos:\n  {cmd}")
