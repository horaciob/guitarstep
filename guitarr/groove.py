"""Groove: where in the beat your timing slips (on the beat, the "and", the sixteenths, triplets) and how even
your attack is (one note louder than the next, downstrokes vs upstrokes)."""
from __future__ import annotations

import numpy as np

from .core import Grid

MIN_HITS = 4          # fewer notes than this in a group say nothing
OFF_MS = 15           # a group that's this early or late on average is worth a word
UNEVEN_PCT = 25       # attack spread (coefficient of variation of the level) that sounds uneven
UPDOWN_DB = 3         # off-beat notes this much softer (or louder) than the on-beat ones

POSITIONS = (("beat", 0.0), ("and", 0.5), ("sixteenth", 0.25), ("sixteenth", 0.75),
             ("triplet", 1 / 3), ("triplet", 2 / 3))


def position(grid: Grid, t: float, tol: float = 0.07) -> str:
    """Which part of the beat a reference time falls on."""
    f = grid.beat_pos(t) % 1.0
    for name, at in POSITIONS:
        if min(abs(f - at), 1 - abs(f - at)) <= tol:
            return name
    return "other"


def timing_by_position(grid: Grid, hits: list[tuple[float, float]]) -> list[dict]:
    """hits = (reference time, deviation in seconds). One row per part of the beat with enough notes."""
    groups: dict[str, list[float]] = {}
    for t, dt in hits:
        groups.setdefault(position(grid, t), []).append(1000 * dt)
    order = ["beat", "and", "sixteenth", "triplet", "other"]
    rows = []
    for name in order:
        x = groups.get(name, [])
        if len(x) < MIN_HITS:
            continue
        mean = float(np.mean(x))
        rows.append(dict(pos=name, n=len(x), mean_ms=round(mean), std_ms=round(float(np.std(x))),
                         tend="on_time" if abs(mean) < OFF_MS else "late" if mean > 0 else "early"))
    return rows


def dynamics(grid: Grid, notes: list[tuple[float, float]]) -> dict | None:
    """notes = (reference time, level 0..1) of single notes. How even the attack is, and on-beat vs off-beat."""
    if len(notes) < 2 * MIN_HITS:
        return None
    amp = np.array([max(a, 1e-4) for _, a in notes])
    spread = float(100 * np.std(amp) / np.mean(amp))
    on = [a for (t, _), a in zip(notes, amp) if position(grid, t) == "beat"]
    off = [a for (t, _), a in zip(notes, amp) if position(grid, t) in ("and", "sixteenth")]
    diff = None
    if len(on) >= MIN_HITS and len(off) >= MIN_HITS:
        diff = round(float(20 * np.log10(np.mean(off) / np.mean(on))), 1)
    code = "even"
    if diff is not None and abs(diff) >= UPDOWN_DB:
        code = "off_softer" if diff < 0 else "off_louder"
    elif spread >= UNEVEN_PCT:
        code = "uneven"
    return dict(n=len(notes), spread_pct=round(spread), offbeat_db=diff, code=code)


def tip(rows: list[dict]) -> dict | None:
    """The one thing to work on: the part of the beat that slips the most (if any slips at all)."""
    bad = [r for r in rows if r["tend"] != "on_time"]
    if not bad:
        return None
    r = max(bad, key=lambda r: abs(r["mean_ms"]))
    return dict(pos=r["pos"], tend=r["tend"], ms=abs(r["mean_ms"]))
