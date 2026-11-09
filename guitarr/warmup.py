"""The daily warm-up: short technical drills with a metronome, in the spirit of a daily workout book.

Every day brings one drill, in a key that walks the circle of fifths and a position that moves along the neck,
so in a few weeks every key and every position comes up. Each drill keeps its own tempo goal: a take the listener
grades at 90% or more, at the goal tempo or faster, raises the goal by 4 BPM. The notes come from the theory
engine (no stored tabs).
"""
from __future__ import annotations

import random
from datetime import date

from . import theory as th

# drill → (positions, notes per beat, starting tempo, uses a key)
DRILLS = {
    "spider": dict(positions=3, per_beat=4, start_bpm=60, uses_key=False),
    "pentatonic": dict(positions=5, per_beat=2, start_bpm=70, uses_key=True),
    "major": dict(positions=7, per_beat=2, start_bpm=60, uses_key=True),
    "arpeggios": dict(positions=3, per_beat=2, start_bpm=60, uses_key=True),
    "octaves": dict(positions=4, per_beat=2, start_bpm=60, uses_key=True),
    "caged": dict(positions=5, per_beat=2, start_bpm=60, uses_key=True),
    "legato": dict(positions=5, per_beat=2, start_bpm=60, uses_key=True),
    "sweep": dict(positions=3, per_beat=3, start_bpm=50, uses_key=True),
}
ORDER = list(DRILLS)
KEYS_CYCLE = [9, 4, 11, 6, 1, 8, 3, 10, 5, 0, 7, 2]          # A E B F# C# Ab Eb Bb F C G D: the circle of fifths
STRINGS = (6, 5, 4, 3, 2, 1)
ARP_STRINGS = (6, 5, 4)                                       # the E, A and D shapes: where the root sits
OCTAVE_PAIRS = ((6, 4), (5, 3), (4, 2), (3, 1))
MINOR_PENT = [0, 3, 5, 7, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
COMFORT = 15                                                  # above this fret, a shape moves down an octave if it fits
RAISE, PASS, MAX_BPM = 4, 90, 220


class WarmupError(ValueError):
    pass


def today_plan(today: date | None = None) -> dict:
    """{drill, key, position} for a day: the drill changes daily; key and position after each round of drills."""
    n = (today or date.today()).toordinal()
    drill = ORDER[n % len(ORDER)]
    lap = n // len(ORDER)
    return dict(drill=drill, key=th.plain_name(KEYS_CYCLE[lap % 12]), position=lap % DRILLS[drill]["positions"])


def surprise(rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    drill = rng.choice(ORDER)
    return dict(drill=drill, key=th.plain_name(rng.randrange(12)), position=rng.randrange(DRILLS[drill]["positions"]))


def _fret_on(string: int, pc: int, lowest: int = 1) -> int:
    f = (pc - th.fret_pitch(string, 0)) % 12
    return f + 12 if f < lowest else f


def _fit(steps: list[tuple]) -> list[tuple]:
    """Moves the whole shape down an octave when it climbs past the comfortable part of the neck."""
    if max(s[1] for s in steps) <= COMFORT or any(s[1] - 12 < 0 for s in steps):
        return steps
    return [(s, f - 12, *rest) for s, f, *rest in steps]


def _up_down(steps: list[tuple]) -> list[tuple]:
    return steps + steps[-2::-1]


def _by_string(root: int, intervals: list[int], per_string: int, start: int) -> list[tuple[int, int]]:
    """n notes per string from scale degree `start` on the low E: two per string in the minor pentatonic gives
    its five boxes; three per string in the major scale gives its seven positions."""
    r = th.fret_pitch(6, _fret_on(6, root))
    pitches: list[int] = []
    octave = 0
    while len(pitches) < start + per_string * 6:
        pitches += [r + 12 * octave + i for i in intervals]
        octave += 1
    seq = pitches[start:]
    return _fit([(s, seq[k * per_string + j] - th.fret_pitch(s, 0)) for k, s in enumerate(STRINGS) for j in range(per_string)])


def _arpeggio(root: int, string: int, third: int) -> list[tuple[int, int]]:
    """A triad in the shape with its root on `string`: chord tones in the four frets around the root, one place per
    pitch, from the root up."""
    f = _fret_on(string, root)
    pcs = {root % 12, (root + third) % 12, (root + 7) % 12}
    found = [(s, fr) for s in STRINGS for fr in range(max(0, f - 1), f + 4)
             if th.fret_pitch(s, fr) % 12 in pcs and (s < string or (s == string and fr >= f))]
    by_pitch: dict[int, tuple[int, int]] = {}
    for s, fr in found:
        by_pitch.setdefault(th.fret_pitch(s, fr), (s, fr))
    return [by_pitch[p] for p in sorted(by_pitch)]


def steps(drill: str, key: str = "A", position: int = 0) -> list[dict]:
    """The notes of a drill in order: [{string, fret, pitch, tech}] (tech: pick, hammer or pull)."""
    if drill not in DRILLS:
        raise WarmupError(f"Unknown drill: {drill}")
    pos = position % DRILLS[drill]["positions"]
    root = th.pc(key)
    if drill == "spider":
        start = 1 + 4 * pos
        up = [(s, start + i) for s in STRINGS for i in range(4)]
        out = up + [(s, start + 3 - i) for s in reversed(STRINGS) for i in range(4)]
    elif drill in ("pentatonic", "legato"):
        out = _up_down(_by_string(root, MINOR_PENT, 2, pos))
    elif drill == "major":
        out = _up_down(_by_string(root, MAJOR, 3, pos))
    elif drill == "arpeggios":                                   # up the major, down the minor: only the 3rd moves
        s = ARP_STRINGS[pos]
        major, minor = _arpeggio(root, s, 4), _arpeggio(root, s, 3)
        top = th.fret_pitch(*major[-1])
        out = _fit(major + [x for x in reversed(minor) if th.fret_pitch(*x) < top])
    elif drill == "octaves":
        low, high = OCTAVE_PAIRS[pos]
        shift = 12 - (th.fret_pitch(high, 0) - th.fret_pitch(low, 0))
        r = _fret_on(low, root)
        out = _fit([x for i in range(6) for x in ((low, r + i), (high, r + i + shift))])
    elif drill == "caged":
        c = th.caged(th.plain_name(root), "maj", th.CAGED_ORDER[pos], max_fret=20)
        out = _fit(_up_down([(s, f) for s, f, _ in c["path"]]))
    else:                                                        # sweep: one major shape, up and back
        out = _fit(_up_down(_arpeggio(root, ARP_STRINGS[pos], 4)))
    result = [dict(string=s, fret=f, pitch=th.fret_pitch(s, f), tech="pick") for s, f in out]
    if drill == "legato":                                        # pick the first note on each string, slur the rest
        for prev, cur in zip(result, result[1:]):
            if prev["string"] == cur["string"]:
                cur["tech"] = "hammer" if cur["pitch"] > prev["pitch"] else "pull"
    return result


def timed(drill: str, key: str, position: int) -> list[dict]:
    """The drill as the listener's timed sequence: an even run of notes, `per_beat` to a beat."""
    per = DRILLS[drill]["per_beat"]
    return [dict(pitch=x["pitch"], start=round(i / per, 4), beats=round(1 / per, 4)) for i, x in enumerate(steps(drill, key, position))]


def position_label(drill: str, position: int) -> dict:
    """{code, params} for the UI: which box, position, shape or strings."""
    pos = position % DRILLS[drill]["positions"]
    if drill == "spider":
        return dict(code="frets", params=dict(lo=1 + 4 * pos, hi=4 + 4 * pos))
    if drill in ("pentatonic", "legato"):
        return dict(code="box", params=dict(n=pos + 1))
    if drill == "major":
        return dict(code="degree", params=dict(n=pos + 1))
    if drill in ("arpeggios", "sweep"):
        return dict(code="shape", params=dict(shape="EAD"[pos]))
    if drill == "octaves":
        low, high = OCTAVE_PAIRS[pos]
        return dict(code="strings", params=dict(a=low, b=high))
    return dict(code="shape", params=dict(shape=th.CAGED_ORDER[pos]))


def goal(saved: dict, drill: str) -> int:
    return int(saved.get(drill, {}).get("bpm") or DRILLS[drill]["start_bpm"])


def next_goal(current: int, played_bpm: float, score: float | None) -> int:
    """A clean take (PASS% or more) at the goal or faster raises the goal; anything else keeps it."""
    if score is not None and score >= PASS and played_bpm >= current:
        return min(MAX_BPM, int(round(played_bpm)) + RAISE)
    return current
