"""Progreso: XP, niveles, racha de días, ejercicios y lecciones aprobados, acordes
dominados (por oído o cámara), récords del minuto de cambio y tutorías fijadas.

Todo se decide en el servidor a partir de lo que el oyente escuchó, y se guarda en
~/.guitarr/progreso.json (lo comparten la interfaz web y la terminal).
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta

from . import config

_lock = threading.Lock()

LEVELS = [(0, "Primeras cuerdas"), (150, "Acompañante"), (400, "Rasgueador"), (800, "Bluesero"),
          (1500, "Guitarrista")]
XP = dict(exercise=15, lesson=40, chord=20)


def _empty() -> dict:
    return dict(xp=0, days=[], lessons=[], exercises={}, chords={}, drills={}, tutorias={}, events=[])


def path():
    return config.HOME / "progreso.json"


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
    """Días seguidos practicando, contando hasta hoy (o hasta ayer si hoy todavía no)."""
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
    return {**d, "streak": streak(d["days"]), "practiced_today": today in d["days"], **{"level": level(d["xp"])}}


def get() -> dict:
    with _lock:
        return view()


def _award(d: dict, xp: int, text: str) -> None:
    d["xp"] += xp
    today = date.today().isoformat()
    if today not in d["days"]:
        d["days"].append(today)
    d["events"] = ([dict(at=datetime.now().isoformat(timespec="seconds"), xp=xp, text=text)] + d["events"])[:30]


def practice_xp(score: float | None) -> int:
    """XP por una práctica con escucha: hasta 20 según el puntaje."""
    if score is None:
        return 0
    return max(2, round(score / 5))


def add_practice(score: float | None, what: str = "Práctica") -> int:
    xp = practice_xp(score)
    if xp:
        with _lock:
            d = _read()
            _award(d, xp, f"{what}: {score:.0f}%")
            _write(d)
    return xp


def chord_mastered(cid: str, via: str) -> dict:
    """via = 'oido' | 'camara'. La primera vez que se domina un acorde suma XP."""
    with _lock:
        d = _read()
        rec = d["chords"].setdefault(cid, {})
        first = not rec
        rec[via] = date.today().isoformat()
        xp = XP["chord"] if first else 0
        _award(d, xp, f"Acorde {cid} ({'por oído' if via == 'oido' else 'con la cámara'})")
        _write(d)
        return dict(xp=xp, first=first, chord=cid)


def pin_tutoria(lid: str, url: str | None) -> dict:
    with _lock:
        d = _read()
        if url:
            d["tutorias"][lid] = url
        else:
            d["tutorias"].pop(lid, None)
        _write(d)
        return d["tutorias"]


def on_session(ctx: dict | None, report: dict) -> dict:
    """Registra una sesión de escucha según su contexto y devuelve lo ganado."""
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
            lid, eid, need = ctx["lesson"], ctx["exercise"], ctx.get("min", 80)
            key = f"{lid}/{eid}"
            passed = score is not None and s.get("judged") == s.get("events") and score >= need
            prev = d["exercises"].get(key)
            out.update(passed=passed, score=score, need=need)
            if score is not None and (prev is None or score > prev):
                d["exercises"][key] = score
            if passed and (prev is None or prev < need):
                _award(d, XP["exercise"], f"Ejercicio aprobado: {ctx.get('title', eid)}")
                out["xp"] += XP["exercise"]
            lesson = catalog.get_lesson(lid)
            done = all(d["exercises"].get(f"{lid}/{e['id']}", -1) >= e.get("min", 80) for e in lesson["exercises"])
            if done and lid not in d["lessons"]:
                d["lessons"].append(lid)
                _award(d, XP["lesson"], f"Lección completa: {lesson['title']}")
                out.update(xp=out["xp"] + XP["lesson"], lesson_done=True)
        elif kind == "chord":
            ok = s.get("judged", 0) > 0 and (s.get("first_try", 0) > 0 or s.get("fixed", 0) > 0)
            out["passed"] = ok
            if ok:
                rec = d["chords"].setdefault(ctx["chord"], {})
                first = not rec
                rec["oido"] = date.today().isoformat()
                if first:
                    _award(d, XP["chord"], f"Acorde {ctx['chord']} (por oído)")
                    out.update(xp=XP["chord"], first=True)
        elif kind == "drill":
            pair = "-".join(ctx["chords"])
            changes = max(0, s.get("first_try", 0) + s.get("fixed", 0) - 1)
            best = d["drills"].get(pair, 0)
            out.update(changes=changes, best=max(best, changes), record=changes > best)
            d["drills"][pair] = max(best, changes)
            xp = changes // 2
            if xp:
                _award(d, xp, f"Minuto de cambio {pair.replace('-', '↔')}: {changes} cambios")
                out["xp"] = xp
        else:
            xp = practice_xp(score) if s.get("judged") else 0
            if xp:
                _award(d, xp, f"Práctica: {report.get('reference', {}).get('name', '')} {score:.0f}%")
                out["xp"] = xp
        _write(d)
        out["progress"] = view(d)
        return out


def print_progress() -> None:
    from . import catalog

    d = get()
    lv = d["level"]
    bar = "█" * int(lv["progress"] * 20)
    print(f"Nivel {lv['level']} · {lv['title']}")
    print(f"  {d['xp']} XP  {bar:20s} " + (f"(próximo nivel: {lv['next_xp']})" if lv["next_xp"] else ""))
    print(f"  🔥 racha: {d['streak']} {'día' if d['streak'] == 1 else 'días'}"
          + ("" if d["practiced_today"] else "  (hoy todavía no practicaste)"))
    all_l = catalog.lessons()
    print(f"  lecciones: {len([x for x in all_l if x['id'] in d['lessons']])}/{len(all_l)}")
    nxt = next((x for x in all_l if x["id"] not in d["lessons"]), None)
    if nxt:
        print(f"    siguiente: {nxt['title']}  (guitarr gui → Ruta)")
    print(f"  acordes dominados: {', '.join(sorted(d['chords'])) or '—'}")
    if d["drills"]:
        print("  minuto de cambio: " + ", ".join(f"{k.replace('-', '↔')} {v}" for k, v in d["drills"].items()))
