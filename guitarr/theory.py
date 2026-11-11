"""Music theory for lessons and tools: spelled notes, intervals, scales, chords, diatonic
harmony, guitar voicings, chord naming and voice leading.

Notes are spelled by letter: "F#" and "Gb" are the same pitch but different names, and every
scale and chord is spelled from its root (F# major has E#, Gb major has Cb). Pitch classes
(0 = C … 11 = B) are used only where spelling doesn't matter.

Guitar positions use the catalog's convention: frets listed from the 6th string (low E) to the
1st, -1 = not played. String numbers are the usual ones: 1 = high E … 6 = low E.
"""
from __future__ import annotations

import re
from itertools import product

LETTERS = "CDEFGAB"
LETTER_PC = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
OPEN = [40, 45, 50, 55, 59, 64]                      # standard tuning, 6th → 1st string
ACC = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2, "♯": 1, "♭": -1, "x": 2}


class TheoryError(ValueError):
    pass


# ---------------------------------------------------------------- notes
def parse_note(name: str) -> tuple[str, int]:
    m = re.fullmatch(r"([A-Ga-g])(##|bb|#|b|♯|♭|x)?", name.strip())
    if not m:
        raise TheoryError(f"Not a note name: {name!r}")
    return m.group(1).upper(), ACC[m.group(2) or ""]


def note_name(letter: str, acc: int) -> str:
    return letter + {0: "", 1: "#", 2: "##", -1: "b", -2: "bb"}[acc]


def pc(name: str) -> int:
    letter, acc = parse_note(name)
    return (LETTER_PC[letter] + acc) % 12


# a plain name for a pitch class when there's no key to spell from
PLAIN = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def plain_name(p: int) -> str:
    return PLAIN[p % 12]


# ---------------------------------------------------------------- intervals
# name → (letter steps, semitones). Compound intervals (9, 11, 13) keep their steps above the octave.
INTERVALS = {
    "P1": (0, 0), "m2": (1, 1), "M2": (1, 2), "A2": (1, 3), "m3": (2, 3), "M3": (2, 4), "d4": (3, 4),
    "P4": (3, 5), "A4": (3, 6), "d5": (4, 6), "P5": (4, 7), "A5": (4, 8), "m6": (5, 8), "M6": (5, 9),
    "d7": (6, 9), "m7": (6, 10), "M7": (6, 11), "P8": (7, 12),
    "m9": (8, 13), "M9": (8, 14), "A9": (8, 15), "P11": (10, 17), "A11": (10, 18), "m13": (12, 20), "M13": (12, 21),
}
# the simple intervals by size, for naming the distance between two pitches
BY_SEMITONES = ["P1", "m2", "M2", "m3", "M3", "P4", "A4", "P5", "m6", "M6", "m7", "M7", "P8"]
# degree labels as written over a chord or scale ("b3", "#11")
DEGREE = {"P1": "1", "m2": "b2", "M2": "2", "A2": "#2", "m3": "b3", "M3": "3", "d4": "b4", "P4": "4", "A4": "#4",
          "d5": "b5", "P5": "5", "A5": "#5", "m6": "b6", "M6": "6", "d7": "bb7", "m7": "b7", "M7": "7", "P8": "1",
          "m9": "b9", "M9": "9", "A9": "#9", "P11": "11", "A11": "#11", "m13": "b13", "M13": "13"}


def transpose(note: str, interval: str) -> str:
    """The note `interval` above `note`, spelled (C + m3 = Eb, not D#)."""
    steps, semis = INTERVALS[interval]
    letter, acc = parse_note(note)
    new_letter = LETTERS[(LETTERS.index(letter) + steps) % 7]
    target = (LETTER_PC[letter] + acc + semis) % 12
    diff = (target - LETTER_PC[new_letter]) % 12
    diff = diff - 12 if diff > 6 else diff
    if not -2 <= diff <= 2:
        raise TheoryError(f"Can't spell {interval} above {note}")
    return note_name(new_letter, diff)


def interval_name(low: int, high: int) -> str:
    """Simple interval between two pitches (MIDI numbers), by semitones (A4 for the tritone)."""
    d = abs(high - low)
    return "P8" if d and d % 12 == 0 else BY_SEMITONES[d % 12]


# ---------------------------------------------------------------- scales
SCALES = {
    "major":            ["P1", "M2", "M3", "P4", "P5", "M6", "M7"],
    "natural_minor":    ["P1", "M2", "m3", "P4", "P5", "m6", "m7"],
    "harmonic_minor":   ["P1", "M2", "m3", "P4", "P5", "m6", "M7"],
    "melodic_minor":    ["P1", "M2", "m3", "P4", "P5", "M6", "M7"],
    "dorian":           ["P1", "M2", "m3", "P4", "P5", "M6", "m7"],
    "phrygian":         ["P1", "m2", "m3", "P4", "P5", "m6", "m7"],
    "phrygian_dominant": ["P1", "m2", "M3", "P4", "P5", "m6", "m7"],
    "lydian":           ["P1", "M2", "M3", "A4", "P5", "M6", "M7"],
    "mixolydian":       ["P1", "M2", "M3", "P4", "P5", "M6", "m7"],
    "locrian":          ["P1", "m2", "m3", "P4", "d5", "m6", "m7"],
    "major_pentatonic": ["P1", "M2", "M3", "P5", "M6"],
    "minor_pentatonic": ["P1", "m3", "P4", "P5", "m7"],
    "blues":            ["P1", "m3", "P4", "d5", "P5", "m7"],
    "whole_tone":       ["P1", "M2", "M3", "A4", "A5", "m7"],
    "half_whole":       ["P1", "m2", "m3", "M3", "A4", "P5", "M6", "m7"],
    "whole_half":       ["P1", "M2", "m3", "P4", "d5", "m6", "M6", "M7"],
    "dominant_bebop":   ["P1", "M2", "M3", "P4", "P5", "M6", "m7", "M7"],
    "major_bebop":      ["P1", "M2", "M3", "P4", "P5", "m6", "M6", "M7"],
    "altered":          ["P1", "m2", "A2", "M3", "A4", "m6", "m7"],
}
# the note that gives each mode its color, against the major or minor scale it most resembles
MODE_COLOR = {"dorian": "M6", "phrygian": "m2", "lydian": "A4", "mixolydian": "m7", "locrian": "d5"}


def scale(key: str, name: str) -> list[dict]:
    """[{note, interval, degree, pc}] for the scale, spelled from `key`."""
    if name not in SCALES:
        raise TheoryError(f"Unknown scale: {name}")
    return [dict(note=transpose(key, iv), interval=iv, degree=DEGREE[iv], pc=(pc(key) + INTERVALS[iv][1]) % 12)
            for iv in SCALES[name]]


def relative_minor(major_key: str) -> str:
    return transpose(major_key, "M6")


# ---------------------------------------------------------------- chords
# quality → (symbol suffix, intervals). Several spellings of the same suffix are accepted by parse_chord.
CHORDS = {
    "maj":   ("", ["P1", "M3", "P5"]),
    "min":   ("m", ["P1", "m3", "P5"]),
    "dim":   ("dim", ["P1", "m3", "d5"]),
    "aug":   ("aug", ["P1", "M3", "A5"]),
    "sus2":  ("sus2", ["P1", "M2", "P5"]),
    "sus4":  ("sus4", ["P1", "P4", "P5"]),
    "6":     ("6", ["P1", "M3", "P5", "M6"]),
    "m6":    ("m6", ["P1", "m3", "P5", "M6"]),
    "maj7":  ("maj7", ["P1", "M3", "P5", "M7"]),
    "7":     ("7", ["P1", "M3", "P5", "m7"]),
    "m7":    ("m7", ["P1", "m3", "P5", "m7"]),
    "m7b5":  ("m7b5", ["P1", "m3", "d5", "m7"]),
    "dim7":  ("dim7", ["P1", "m3", "d5", "d7"]),
    "mmaj7": ("m(maj7)", ["P1", "m3", "P5", "M7"]),
    "7sus4": ("7sus4", ["P1", "P4", "P5", "m7"]),
    "maj9":  ("maj9", ["P1", "M3", "P5", "M7", "M9"]),
    "9":     ("9", ["P1", "M3", "P5", "m7", "M9"]),
    "m9":    ("m9", ["P1", "m3", "P5", "m7", "M9"]),
    "m11":   ("m11", ["P1", "m3", "P5", "m7", "M9", "P11"]),
    "13":    ("13", ["P1", "M3", "P5", "m7", "M9", "M13"]),
    "7b9":   ("7b9", ["P1", "M3", "P5", "m7", "m9"]),
    "7#9":   ("7#9", ["P1", "M3", "P5", "m7", "A9"]),
    "7#11":  ("7#11", ["P1", "M3", "P5", "m7", "A11"]),
    "7b13":  ("7b13", ["P1", "M3", "P5", "m7", "m13"]),
}
ALIASES = {"": "maj", "M": "maj", "maj": "maj", "m": "min", "min": "min", "-": "min", "°": "dim", "o": "dim",
           "+": "aug", "Δ7": "maj7", "M7": "maj7", "Δ": "maj7", "-7": "m7", "min7": "m7", "ø": "m7b5", "ø7": "m7b5",
           "m7(b5)": "m7b5", "°7": "dim7", "o7": "dim7", "mmaj7": "mmaj7", "mM7": "mmaj7", "m(maj7)": "mmaj7",
           "sus": "sus4"}
ALIASES.update({suffix: q for q, (suffix, _) in CHORDS.items()})


def parse_chord(symbol: str) -> dict:
    """"Bbm7b5/E" → {root, quality, bass, symbol}."""
    m = re.fullmatch(r"([A-G](?:##|bb|#|b)?)(.*?)(?:/([A-G](?:##|bb|#|b)?))?", symbol.strip())
    if not m or m.group(2) not in ALIASES:
        raise TheoryError(f"Unknown chord: {symbol!r}")
    root, quality, bass = m.group(1), ALIASES[m.group(2)], m.group(3)
    return dict(root=root, quality=quality, bass=bass, symbol=chord_symbol(root, quality, bass))


def chord_symbol(root: str, quality: str, bass: str | None = None) -> str:
    return root + CHORDS[quality][0] + (f"/{bass}" if bass else "")


def chord(symbol: str) -> dict:
    """{symbol, root, quality, bass, tones: [{note, interval, degree, pc}]} for a chord symbol."""
    c = parse_chord(symbol)
    tones = [dict(note=transpose(c["root"], iv), interval=iv, degree=DEGREE[iv], pc=(pc(c["root"]) + INTERVALS[iv][1]) % 12)
             for iv in CHORDS[c["quality"]][1]]
    return {**c, "tones": tones}


def tone(ch: dict, degree: str) -> dict:
    """A chord tone by its degree label ("1", "3", "b3", "7", "b7"…); "3" and "7" match their flat forms too."""
    for t in ch["tones"]:
        if t["degree"] == degree or t["degree"].lstrip("b#") == degree.lstrip("b#") and degree in ("3", "5", "7"):
            return t
    raise TheoryError(f"{ch['symbol']} has no {degree}")


def name_chord(pitches: list[int]) -> list[str]:
    """Names for a set of pitches (MIDI numbers, lowest = bass), best first: exact chords with the bass as
    root, then inversions written as slash chords."""
    if not pitches:
        return []
    pcs = sorted({p % 12 for p in pitches})
    bass = min(pitches) % 12
    found: list[tuple[int, str]] = []
    for root in pcs:
        shape = sorted({(p - root) % 12 for p in pcs})
        for q, (_, ivs) in CHORDS.items():
            if sorted({INTERVALS[iv][1] % 12 for iv in ivs}) == shape:
                rname = plain_name(root)
                name = chord_symbol(rname, q)
                if bass != root:
                    name += "/" + spell_in(rname, q, bass)
                found.append((0 if bass == root else 1, len(ivs), name))
    return [n for _, _, n in sorted(found)]


def spell_in(root: str, quality: str, p: int) -> str:
    """How pitch class p is spelled inside the chord (the E in C/E, not Fb)."""
    for iv in CHORDS[quality][1]:
        n = transpose(root, iv)
        if pc(n) == p % 12:
            return n
    return plain_name(p)


# ---------------------------------------------------------------- diatonic harmony
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]
_TRIAD = {(4, 7): "maj", (3, 7): "min", (3, 6): "dim", (4, 8): "aug"}
_SEVENTH = {(4, 7, 11): "maj7", (4, 7, 10): "7", (3, 7, 10): "m7", (3, 6, 10): "m7b5", (3, 6, 9): "dim7",
            (3, 7, 11): "mmaj7", (4, 8, 11): "maj7"}
_NINTH = {"maj7": "maj9", "7": "9", "m7": "m9"}


def harmonize(key: str, scale_name: str = "major", size: str = "triads") -> list[dict]:
    """Chords built on every degree by stacking scale thirds. size: triads | sevenths | ninths.
    Each: {degree, roman, symbol, quality, notes}. Ninths that aren't a plain maj9/9/m9 stay sevenths."""
    sc = scale(key, scale_name)
    if len(sc) != 7:
        raise TheoryError("Harmonize needs a seven-note scale")
    out = []
    for i in range(7):
        stack = [sc[(i + 2 * k) % 7] for k in range(5)]
        semis = [(s["pc"] - stack[0]["pc"]) % 12 for s in stack]
        triad = _TRIAD.get((semis[1], semis[2]), "maj")
        seventh = _SEVENTH.get((semis[1], semis[2], semis[3]))
        if size == "triads" or seventh is None:
            q, n = triad, 3
        elif size == "ninths" and seventh in _NINTH and semis[4] == 2:
            q, n = _NINTH[seventh], 5
        else:
            q, n = seventh, 4
        out.append(dict(degree=i + 1, roman=roman(i, q), symbol=chord_symbol(stack[0]["note"], q), quality=q,
                        notes=[s["note"] for s in stack[:n]]))
    return out


def roman(i: int, quality: str) -> str:
    base = ROMAN[i]
    minor = quality in ("min", "m7", "m9", "m11", "m6", "mmaj7", "m7b5", "dim", "dim7")
    r = base.lower() if minor else base
    return r + {"dim": "°", "dim7": "°7", "m7b5": "ø7", "aug": "+", "maj7": "maj7", "7": "7", "m7": "7", "maj9": "maj9",
                "9": "9", "m9": "9", "mmaj7": "(maj7)"}.get(quality, "")


def tritone_sub(symbol: str) -> str:
    """The dominant a tritone away (G7 → Db7): same 3rd and 7th, swapped."""
    c = parse_chord(symbol)
    return chord_symbol(transpose(c["root"], "d5"), c["quality"] if c["quality"] in ("7", "9", "13", "7b9", "7#9", "7#11", "7b13") else "7")


# the scale a jazz player hears over each chord type (for eighth-note lines)
CHORD_SCALE = {"maj7": "major", "maj": "major", "6": "major", "maj9": "major", "7": "mixolydian", "9": "mixolydian",
               "13": "mixolydian", "7b9": "half_whole", "7#9": "altered", "7#11": "lydian", "7b13": "altered",
               "m7": "dorian", "min": "dorian", "m9": "dorian", "m6": "melodic_minor", "m11": "dorian",
               "m7b5": "locrian", "dim7": "whole_half", "dim": "whole_half", "mmaj7": "melodic_minor"}


# ---------------------------------------------------------------- the staff
# Guitar is written in the treble clef an octave above how it sounds (the small 8 under the clef).
STAFF_MIDDLE = LETTERS.index("B") + 7 * 4             # the middle line of the treble clef: written B4


def staff_note(sounding: int, flats: bool = False) -> dict:
    """Where a guitar note is written: {step, acc, name}. step counts letter steps from the middle line (+ is up,
    each step is half a space); acc is 1 (sharp), -1 (flat) or 0; black keys are sharps unless `flats`."""
    written = sounding + 12
    p, octave = written % 12, written // 12 - 1
    acc = 0
    if p not in LETTER_PC.values():
        acc = -1 if flats else 1
        p = (p - acc) % 12
    letter = next(k for k, v in LETTER_PC.items() if v == p)
    step = LETTERS.index(letter) + 7 * octave - STAFF_MIDDLE
    return dict(step=step, acc=acc, name=note_name(letter, acc))


# ---------------------------------------------------------------- guitar positions
def fret_pitch(string: int, fret: int) -> int:
    return OPEN[6 - string] + fret


def positions(pcs: set[int], lo: int = 0, hi: int = 12, strings=(6, 5, 4, 3, 2, 1)) -> list[tuple[int, int, int]]:
    """Every (string, fret, pitch) in the fret range whose pitch class is in pcs."""
    return [(s, f, fret_pitch(s, f)) for s in strings for f in range(lo, hi + 1) if fret_pitch(s, f) % 12 in pcs]


def scale_path(key: str, scale_name: str, lo: int, hi: int, direction: str = "up", string: int | None = None,
               nps: int = 0, octaves: int = 1) -> list[tuple[int, int, int]]:
    """A playable run: [(string, fret, pitch)] from the lowest root in the fret range up through
    `octaves` octaves (and back down when direction = "updown").
    - string: stay on one string (frets lo…hi).
    - nps: notes per string (3 = three-notes-per-string) starting on the 6th string at the root ≥ lo."""
    sc = scale(key, scale_name)
    pcs = [s["pc"] for s in sc]
    root = pcs[0]
    if nps:
        start = next(f for f in range(lo, lo + 12) if fret_pitch(6, f) % 12 == root)
        p0 = fret_pitch(6, start)
        seq = [p for p in range(p0, p0 + 12 * octaves + 1) if p % 12 in pcs]
        run, s = [], 6
        for k in range(0, len(seq), nps):
            for p in seq[k:k + nps]:
                run.append((s, p - OPEN[6 - s], p))
            s -= 1
            if s < 1:
                break
        run = [r for r in run if r[1] >= 0]
    else:
        strings = (string,) if string else (6, 5, 4, 3, 2, 1)
        cands = positions(set(pcs), lo, hi, strings)
        roots = sorted(p for _, _, p in cands if p % 12 == root)
        if not roots:
            raise TheoryError(f"No {key} between frets {lo} and {hi}")
        p0, p1 = roots[0], roots[0] + 12 * octaves
        if p1 > max(p for _, _, p in cands):
            p1 = max(p for p in roots if p > p0) if len(roots) > 1 else max(p for _, _, p in cands)
        run, used = [], set()
        for s in strings:                                   # low string first, ascending frets
            for st, f, p in sorted((c for c in cands if c[0] == s), key=lambda c: c[1]):
                if p0 <= p <= p1 and p not in used and (not run or p > run[-1][2]):
                    run.append((st, f, p))
                    used.add(p)
    if direction == "updown":
        run = run + run[-2::-1]
    elif direction == "down":
        run = run[::-1]
    return run


def arpeggio_path(symbol: str, lo: int, hi: int, direction: str = "up", octaves: int = 1) -> list[tuple[int, int, int]]:
    """Chord tones as a run, like scale_path."""
    ch = chord(symbol)
    pcs = [t["pc"] for t in ch["tones"]]
    cands = positions(set(pcs), lo, hi)
    roots = sorted(p for _, _, p in cands if p % 12 == pcs[0])
    if not roots:
        raise TheoryError(f"No {ch['root']} between frets {lo} and {hi}")
    p0 = roots[0]
    p1 = min(p0 + 12 * octaves, max(p for _, _, p in cands))
    run, used = [], set()
    for s in (6, 5, 4, 3, 2, 1):
        for st, f, p in sorted((c for c in cands if c[0] == s), key=lambda c: c[1]):
            if p0 <= p <= p1 and p not in used and (not run or p > run[-1][2]):
                run.append((st, f, p))
                used.add(p)
    if direction == "updown":
        run = run + run[-2::-1]
    elif direction == "down":
        run = run[::-1]
    return run


# ---------------------------------------------------------------- CAGED
# The five open-chord shapes moved up the neck. Each one: the string that holds the root, where the 4-fret
# window starts from that root fret (C and G reach back from it), in the order they follow up the neck.
CAGED = {"C": dict(string=5, offset=-3), "A": dict(string=5, offset=0), "G": dict(string=6, offset=-3),
         "E": dict(string=6, offset=0), "D": dict(string=4, offset=0)}
CAGED_ORDER = "CAGED"
CAGED_WIDTH = 3


def caged(root: str, quality: str = "maj", shape: str = "E", max_fret: int = 15) -> dict:
    """One CAGED shape of a chord → {shape, lo, hi, root_fret, path: [(string, fret, pitch)] low to high}.
    The root goes on the lowest fret of its string that keeps the whole window on the neck."""
    if shape not in CAGED:
        raise TheoryError(f"Unknown CAGED shape: {shape}")
    sh = CAGED[shape]
    pcs = {t["pc"] for t in chord(chord_symbol(root, quality))["tones"]}
    rpc = pc(root)
    rf = next(f for f in range(max(0, -sh["offset"]), 24) if fret_pitch(sh["string"], f) % 12 == rpc)
    lo = rf + sh["offset"]
    hi = lo + CAGED_WIDTH
    if hi > max_fret:
        raise TheoryError(f"The {shape} shape of {root} doesn't fit below fret {max_fret}")
    by_pitch: dict[int, tuple[int, int, int]] = {}
    for s_ in (6, 5, 4, 3, 2, 1):
        for f in range(lo, hi + 1):
            p = fret_pitch(s_, f)
            if p % 12 in pcs and p not in by_pitch:
                by_pitch[p] = (s_, f, p)
    return dict(shape=shape, lo=lo, hi=hi, root_fret=rf, path=[by_pitch[p] for p in sorted(by_pitch)])


def caged_along(root: str, quality: str = "maj", shapes: str = CAGED_ORDER) -> list[dict]:
    """The shapes of one chord that fit on the neck, sorted up the neck."""
    out = []
    for k in shapes:
        try:
            out.append(caged(root, quality, k))
        except TheoryError:
            pass
    return sorted(out, key=lambda c: c["lo"])


# ---------------------------------------------------------------- voicings
# string sets, low string first
SETS = {"123": (3, 2, 1), "234": (4, 3, 2), "345": (5, 4, 3), "456": (6, 5, 4),
        "1234": (4, 3, 2, 1), "2345": (5, 4, 3, 2), "3456": (6, 5, 4, 3),
        "6432": (6, 4, 3, 2), "5321": (5, 3, 2, 1),          # drop-3: one string skipped above the bass
        "643": (6, 4, 3), "543": (5, 4, 3)}                    # shells
VOICING_SETS = {"triad": ("123", "234", "345", "456"), "drop2": ("1234", "2345", "3456"),
                "drop3": ("6432", "5321"), "shell": ("643", "543")}


def voice_orders(ch: dict, kind: str) -> list[list[str]]:
    """The chord-tone orders (low → high) a voicing kind uses, one per inversion."""
    degs = [t["degree"] for t in ch["tones"]]
    if kind == "triad":
        d = degs[:3]
        return [d[k:] + d[:k] for k in range(3)]
    if kind == "shell":
        return [[degs[0], degs[3], degs[1]], [degs[0], degs[1], degs[3]]]   # 1-7-3 and 1-3-7
    # four-note voicings: a seventh chord as written; with a 9th (or more), leave out the root (3 5 7 9),
    # as jazz guitarists do, so the color tone is in the chord
    four = degs[1:5] if len(degs) >= 5 else degs[:4]
    closes = [four[k:] + four[:k] for k in range(4)]                         # close position, low → high
    if kind == "drop2":
        return [[c[2], c[0], c[1], c[3]] for c in closes]
    if kind == "drop3":
        return [[c[1], c[0], c[2], c[3]] for c in closes]
    raise TheoryError(f"Unknown voicing: {kind}")


def fit(ch: dict, order: list[str], strings: tuple[int, ...], lo: int = 0, hi: int = 15, span: int = 4) -> list[list[int]]:
    """Every way to play the chord tones `order` on `strings` (low → high) within `span` frets, with pitches
    rising string to string. Returns frets lists (6th → 1st, -1 = muted), lowest position first."""
    pcs = [tone(ch, d)["pc"] for d in order]
    options = [[f for f in range(lo, hi + 1) if fret_pitch(s, f) % 12 == p] for s, p in zip(strings, pcs)]
    out = []
    for combo in product(*options):
        pressed = [f for f in combo if f > 0]
        if pressed and max(pressed) - min(pressed) > span - 1:
            continue
        if 0 in combo and pressed and max(pressed) > 5:          # an open string only works near the nut
            continue
        pitches = [fret_pitch(s, f) for s, f in zip(strings, combo)]
        if any(b <= a for a, b in zip(pitches, pitches[1:])):
            continue
        frets = [-1] * 6
        for s, f in zip(strings, combo):
            frets[6 - s] = f
        out.append(frets)
    out.sort(key=lambda fr: (min([f for f in fr if f > 0] or [0]), fr))
    return out


def voicings(symbol: str, kind: str, lo: int = 0, hi: int = 15) -> list[dict]:
    """All voicings of a kind for a chord: [{frets, strings, order, inversion, position, name}]."""
    ch = chord(symbol)
    if kind in ("drop2", "drop3", "shell") and len(ch["tones"]) < 4:
        raise TheoryError(f"{kind} needs a seventh chord")
    out, seen = [], set()
    for inv, order in enumerate(voice_orders(ch, kind)):
        for set_id in VOICING_SETS[kind]:
            for frets in fit(ch, order, SETS[set_id], lo, hi):
                key = tuple(frets)
                if key in seen:
                    continue
                seen.add(key)
                pressed = [f for f in frets if f > 0]
                out.append(dict(frets=frets, strings=set_id, order=order, inversion=inv,
                                position=min(pressed) if pressed else 0, name=symbol))
    out.sort(key=lambda v: (v["position"], v["strings"], v["inversion"]))
    return out


def shape_pitches(frets: list[int]) -> list[int]:
    return [OPEN[i] + f for i, f in enumerate(frets) if f >= 0]


# ---------------------------------------------------------------- voice leading
def voice_lead(progression: list[str], kind: str, lead: str = "smooth", start: int = 3, sets: tuple[str, ...] | None = None) -> list[dict]:
    """A voicing per chord, each chosen to move as little as possible from the previous one.
    lead: "smooth" (least total movement), "top" (top note closest) or "bass" (bass closest).
    The first chord is the voicing nearest to fret `start`."""
    out: list[dict] = []
    for sym in progression:
        cands = [v for v in voicings(sym, kind) if not sets or v["strings"] in sets]
        if not cands:
            raise TheoryError(f"No {kind} voicing for {sym}")
        if not out:
            best = min(cands, key=lambda v: (abs(v["position"] - start), v["position"]))
        else:
            prev = shape_pitches(out[-1]["frets"])

            def cost(v):
                cur = shape_pitches(v["frets"])
                if lead == "top":
                    return (abs(cur[-1] - prev[-1]), _moved(prev, cur))
                if lead == "bass":
                    return (abs(cur[0] - prev[0]), _moved(prev, cur))
                return (_moved(prev, cur), abs(v["position"] - out[-1]["position"]))
            best = min(cands, key=cost)
        out.append(best)
    return out


def _moved(a: list[int], b: list[int]) -> int:
    """Total semitones the voices move (voices matched low to high; extra voices count from the nearest)."""
    if len(a) == len(b):
        return sum(abs(x - y) for x, y in zip(sorted(a), sorted(b)))
    return sum(min(abs(x - y) for y in b) for x in a) + sum(min(abs(x - y) for x in a) for y in b)


def guide_line(progression: list[str], lo: int = 1, hi: int = 10, per_chord: int = 1) -> list[tuple[int, int, int]]:
    """A single-note line through the 3rds and 7ths: each chord's guide tone nearest to the last note
    (per_chord = 2 plays both, nearest first). Starts on the first chord's 3rd, low in the fret range."""
    run: list[tuple[int, int, int]] = []
    for sym in progression:
        ch = chord(sym)
        want = [tone(ch, "3")["pc"], tone(ch, "7")["pc"]]
        cands = [c for c in positions(set(want), lo, hi, strings=(4, 3, 2))]
        if not cands:
            raise TheoryError(f"No guide tones for {sym} between frets {lo} and {hi}")
        last = run[-1][2] if run else None
        picked = []
        for _ in range(per_chord):
            pool = [c for c in cands if c[2] % 12 not in {p[2] % 12 for p in picked}]
            if last is None:
                best = min((c for c in pool if c[2] % 12 == want[0]), key=lambda c: c[2], default=min(pool, key=lambda c: c[2]))
            else:
                best = min(pool, key=lambda c: (abs(c[2] - last), c[1]))
            picked.append(best)
            last = best[2]
        run += picked
    return run


# ---------------------------------------------------------------- jazz lines
JAZZ_STYLES = ("arpeggio", "approach", "enclosure", "eighths", "walking")


def _place(pitches: list[int], lo: int, hi: int, strings=(6, 5, 4, 3, 2, 1)) -> list[tuple[int, int, int]]:
    """Puts each pitch on a string inside the fret window, staying on (or near) the string of the last note."""
    out, prev = [], None
    for p in pitches:
        cands = [(s, p - OPEN[6 - s]) for s in strings if lo <= p - OPEN[6 - s] <= hi]
        if not cands:
            raise TheoryError(f"{plain_name(p)} doesn't fit between frets {lo} and {hi}")
        s, f = min(cands, key=lambda c: ((abs(c[0] - prev) if prev else -c[0]), c[1]))
        out.append((s, f, p))
        prev = s
    return out


def _playable(lo: int, hi: int, strings=(6, 5, 4, 3, 2, 1)) -> set[int]:
    return {OPEN[6 - s] + f for s in strings for f in range(lo, hi + 1)}


def _near(pcs, ref: int, ok: set[int], above: bool | None = None) -> int:
    """The playable pitch with one of these pitch classes nearest to ref (optionally only above/below it)."""
    cands = [p for p in ok if p % 12 in pcs and (above is None or (p > ref if above else p < ref))]
    if not cands:
        raise TheoryError("No playable note in that direction")
    return min(cands, key=lambda p: (abs(p - ref), p))


def jazz_line(progression: list[str], style: str, lo: int, hi: int, start: str = "3", direction: str = "up") -> list[tuple[int, int, int]]:
    """Generated practice lines over a progression, kept inside a fret window:
    - arpeggio: four chord tones per chord, starting on the tone nearest the last note.
    - approach: a chromatic note below (or the scale step above, every other chord) into a chord tone.
    - enclosure: scale step above, half step below, then the target chord tone.
    - eighths: eight notes of the chord's scale from a chord tone (start: 1, 3 or 7).
    - walking: a bass line, four quarter notes per chord ending with a half-step approach to the next root.
    """
    if style not in JAZZ_STYLES:
        raise TheoryError(f"Unknown line style: {style}")
    chords = [chord(s) for s in progression]
    strings = (6, 5, 4) if style == "walking" else (6, 5, 4, 3, 2, 1)
    ok = _playable(lo, hi, strings)
    top, bottom = max(ok), min(ok)
    pitches: list[int] = []
    up = direction != "down"
    for i, ch in enumerate(chords):
        tones = [t["pc"] for t in ch["tones"][:4]]
        target_pc = tone(ch, start)["pc"] if style != "walking" else tones[0]
        ref = pitches[-1] if pitches else (bottom + 4 if up else top - 4)
        if style == "walking":
            root = _near({tones[0]}, ref, ok)
            third, fifth = tone(ch, "3")["pc"], tone(ch, "5")["pc"]
            a = _near({third}, root, ok, above=True) if root + 4 <= top else _near({third}, root, ok, above=False)
            b = _near({fifth}, a, ok)
            nxt = chords[(i + 1) % len(chords)]["tones"][0]["pc"]
            next_root = _near({nxt}, b, ok)
            app = next_root - 1 if next_root - 1 in ok and next_root - 1 != b else next_root + 1
            pitches += [root, a, b, app]
            continue
        if style == "arpeggio":
            first = _near({target_pc} if not pitches else set(tones), ref, ok)
            go_up = up if not pitches else first + 12 <= top
            seq, p = [first], first
            for _ in range(3):
                p = _near(set(tones), p, ok, above=go_up)
                seq.append(p)
            pitches += seq
            continue
        sc = {s["pc"] for s in scale(ch["root"], CHORD_SCALE.get(ch["quality"], "major"))}
        target = _near({target_pc}, ref, ok)
        if target + 1 > top or target - 1 < bottom:                        # keep room around the target
            target = _near({target_pc}, (top + bottom) // 2, ok)
        step_above = _near(sc, target, ok, above=True)
        if style == "approach":
            lead = target - 1 if i % 2 == 0 else step_above
            go_up = target + 8 <= top
            seq, p = [lead, target], target
            for _ in range(2):
                p = _near(set(tones), p, ok, above=go_up)
                seq.append(p)
            pitches += seq
        elif style == "enclosure":
            go_up = target + 8 <= top
            pitches += [step_above, target - 1, target, _near(set(tones), target, ok, above=go_up)]
        else:                                                                # eighths
            go_up = up if target + 12 <= top else False
            if not go_up and target - 12 < bottom:
                go_up = True
            seq, p = [target], target
            while len(seq) < 8:
                p = _near(sc, p, ok, above=go_up)
                seq.append(p)
            pitches += seq
    return _place(pitches, lo, hi, strings)


def guide_tones(progression: list[str], strings: tuple[int, int] = (4, 3), lo: int = 1, hi: int = 12) -> list[dict]:
    """The 3rd and 7th of each chord as two-note shapes on two adjacent strings, alternating which one is on
    top so each voice moves by step or not at all."""
    out: list[dict] = []
    for sym in progression:
        ch = chord(sym)
        cands = []
        for order in (["3", "7"], ["7", "3"]):
            for frets in fit(ch, order, strings, lo, hi, span=3):
                cands.append(dict(frets=frets, order=order, name=sym))
        if not cands:
            raise TheoryError(f"No guide tones for {sym} on strings {strings}")
        if not out:
            best = min(cands, key=lambda v: max(v["frets"]))
        else:
            prev = shape_pitches(out[-1]["frets"])
            best = min(cands, key=lambda v: _moved(prev, shape_pitches(v["frets"])))
        out.append(best)
    return out
