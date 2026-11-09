"""Reading rhythm: a compact notation for one bar of 4/4, and grading taps against it.

Notation: one token per note or rest, separated by spaces.
- `w h q e s`: whole, half, quarter, eighth, sixteenth.
- `r` in front is a rest of that value: `rq` = quarter rest.
- `.` after it adds half its value: `q.` = dotted quarter (1.5 beats).
- `t` in front is a triplet of that value (2/3 of it): `te te te` = three eighths in one beat.

Taps are graded like the listener grades onsets: each written note is paired with the nearest tap inside a
window, and the distance in milliseconds sets its grade.
"""
from __future__ import annotations

import random
import re

BEATS = dict(w=4.0, h=2.0, q=1.0, e=0.5, s=0.25)
_TOKEN = re.compile(r"^(r?)(t?)([whqes])(\.?)$")

# grading windows (ms) and what each grade is worth
PERFECT_MS, GOOD_MS, OK_MS = 45, 90, 160
WEIGHT = dict(perfect=1.0, good=0.8, early=0.4, late=0.4, miss=0.0)
EXTRA_PENALTY, MAX_PENALTY = 0.1, 0.5
PASS_ITEM = 70                                      # a bar counts as "right" from this accuracy (%)


class RhythmError(ValueError):
    pass


def parse(pattern: str) -> list[dict]:
    """→ [{figure, rest, dotted, triplet, beats}] for a pattern string."""
    out = []
    for tok in pattern.split():
        m = _TOKEN.match(tok)
        if not m:
            raise RhythmError(f"Unknown rhythm token: {tok}")
        rest, trip, fig, dot = m.groups()
        beats = BEATS[fig] * (1.5 if dot else 1.0) * (2 / 3 if trip else 1.0)
        out.append(dict(figure=fig, rest=bool(rest), dotted=bool(dot), triplet=bool(trip), beats=beats))
    if not out:
        raise RhythmError("An empty rhythm")
    return out


def total_beats(pattern: str) -> float:
    return round(sum(e["beats"] for e in parse(pattern)), 3)


def onsets(pattern: str) -> list[float]:
    """Where each note (not rest) starts, in beats from the start of the bar."""
    out, at = [], 0.0
    for e in parse(pattern):
        if not e["rest"]:
            out.append(round(at, 4))
        at += e["beats"]
    return out


def timed(pattern: str, pitch: int, start: float = 0.0) -> list[dict]:
    """The notes of a pattern as the listener's timed sequence ({pitch, start, beats}), one pitch for all."""
    out, at = [], start
    for e in parse(pattern):
        if not e["rest"]:
            out.append(dict(pitch=pitch, start=round(at, 4), beats=round(e["beats"], 4)))
        at += e["beats"]
    return out


def score(expected_ms: list[float], taps_ms: list[float]) -> dict:
    """Pairs each written note with the nearest unused tap within OK_MS.
    → {hits: [{at, offset, grade}], extra, accuracy (0–100), mean_abs}"""
    used: set[int] = set()
    hits = []
    for exp in expected_ms:
        best, dist = -1, float("inf")
        for i, tap in enumerate(taps_ms):
            d = abs(tap - exp)
            if i not in used and d < dist and d <= OK_MS:
                best, dist = i, d
        if best < 0:
            hits.append(dict(at=round(exp), offset=None, grade="miss"))
            continue
        used.add(best)
        off = taps_ms[best] - exp
        a = abs(off)
        grade = "perfect" if a <= PERFECT_MS else "good" if a <= GOOD_MS else "late" if off > 0 else "early"
        hits.append(dict(at=round(exp), offset=round(off), grade=grade))
    extra = len(taps_ms) - len(used)
    raw = sum(WEIGHT[h["grade"]] for h in hits) / max(1, len(hits))
    acc = max(0.0, raw - min(MAX_PENALTY, extra * EXTRA_PENALTY))
    matched = [abs(h["offset"]) for h in hits if h["offset"] is not None]
    return dict(hits=hits, extra=extra, accuracy=round(100 * acc, 1),
                mean_abs=round(sum(matched) / len(matched)) if matched else None)


def grade_taps(pattern: str, bpm: float, taps_ms) -> dict:
    """Taps (ms after the first beat of the bar) against a pattern at a tempo."""
    try:
        taps = [float(x) for x in taps_ms][:64]
    except (TypeError, ValueError):
        taps = []
    beat_ms = 60000.0 / bpm
    return score([b * beat_ms for b in onsets(pattern)], taps)


def lookalikes(rng: random.Random, pattern: str, pool: list[str], n: int = 4) -> list[str]:
    """`pattern` plus n-1 others from the pool for a dictation, preferring ones with the same number of notes
    (so you have to hear where they fall, not just count them). Bars that sound the same as the answer (the same
    attacks, like `h h` and `q rq q rq`) are left out: a dictation only hears where notes start."""
    k, heard = len(onsets(pattern)), onsets(pattern)
    others, seen = [], {tuple(heard)}
    for p in dict.fromkeys(pool):
        if tuple(onsets(p)) not in seen:
            seen.add(tuple(onsets(p)))
            others.append(p)
    rng.shuffle(others)
    others.sort(key=lambda p: abs(len(onsets(p)) - k))
    opts = [pattern] + others[:n - 1]
    rng.shuffle(opts)
    return opts
