"""A song's theory, read from its notes: the key, the chords of the key it uses (and the ones from outside),
the progression that repeats most, and a bar-by-bar reading (chord, degree, job, resting note, scales that fit).

It works on any reference (Guitar Pro, MIDI, MusicXML): only pitches, durations and the bar grid are used.
Every guess is a guess: short passages can mix up relative keys (G major and E minor share every note).
"""
from __future__ import annotations

from . import theory as th
from .core import Reference

# Krumhansl–Kessler key profiles: how much each degree "belongs" to a major or minor key
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]
# the chords a bar can be heard as (intervals from the root) and how much more evidence the rarer ones need
CHORD_SHAPES = {"maj": [0, 4, 7], "min": [0, 3, 7], "7": [0, 4, 7, 10], "m7": [0, 3, 7, 10], "maj7": [0, 4, 7, 11],
                "dim": [0, 3, 6], "m7b5": [0, 3, 6, 10], "sus4": [0, 5, 7], "sus2": [0, 2, 7], "5": [0, 7]}
RARITY = {"7": 0.1, "m7": 0.1, "sus2": 0.1, "sus4": 0.1, "dim": 0.12, "maj7": 0.14, "m7b5": 0.14, "5": 0.05}
MINORISH = {"min", "m7", "dim", "m7b5"}
SUFFIX = {"maj": "", "min": "m", "7": "7", "m7": "m7", "maj7": "maj7", "dim": "°", "m7b5": "m7b5", "sus4": "sus4", "sus2": "sus2", "5": "5"}
ROMAN_SUFFIX = {"dim": "°", "7": "7", "m7": "7", "maj7": "maj7", "m7b5": "ø7", "sus4": "sus4", "sus2": "sus2", "5": "5"}
JOBS = ["tonic", "subdominant", "tonic", "subdominant", "dominant", "tonic", "dominant"]
FIT_SCALES = ["major", "natural_minor", "major_pentatonic", "minor_pentatonic", "blues", "dorian", "mixolydian",
              "harmonic_minor", "lydian", "phrygian"]
NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
FLAT_KEYS = {(5, "major"), (10, "major"), (3, "major"), (8, "major"), (1, "major"), (6, "major"),
             (2, "minor"), (7, "minor"), (0, "minor"), (5, "minor"), (10, "minor"), (3, "minor")}


def _corr(a: list[float], b: list[float]) -> float:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def estimate_key(hist: list[float]) -> list[dict]:
    """Every key, best first: [{root (pitch class), mode, score}]. hist: weight per pitch class."""
    out = []
    for r in range(12):
        rot = [hist[(i + r) % 12] for i in range(12)]
        out.append(dict(root=r, mode="major", score=_corr(rot, MAJOR_PROFILE)))
        out.append(dict(root=r, mode="minor", score=_corr(rot, MINOR_PROFILE)))
    return sorted(out, key=lambda k: -k["score"])


def detect_chord(hist: list[float], bass: list[float] | None = None) -> dict | None:
    """The chord that best explains a bar: {root, quality, fit (share of the bar's weight its notes cover)}."""
    total = sum(hist)
    if total <= 0:
        return None
    bass = bass or [0.0] * 12
    btotal = sum(bass) or 1.0
    best, best_score = None, float("-inf")
    for root in range(12):
        if hist[root] < total * 0.04:                    # the root has to sound
            continue
        for q, ivs in CHORD_SHAPES.items():
            covered = sum(hist[(root + i) % 12] for i in ivs)
            missing = sum((0.4 if i == 7 else 1.0) for i in ivs if hist[(root + i) % 12] < total * 0.04)
            score = covered - 0.6 * (total - covered) - 0.25 * total * missing - RARITY.get(q, 0) * total \
                + 0.35 * total * bass[root] / btotal
            if score > best_score:
                best, best_score = dict(root=root, quality=q, fit=round(covered / total, 2)), score
    return best


def _name(p: int, flats: bool) -> str:
    return (NAMES_FLAT if flats else NAMES_SHARP)[p % 12]


def roman_of(root: int, quality: str, key_root: int, mode: str) -> str:
    """The degree of a chord in a key: vi, ♭VII, V7, #vii°…"""
    steps = MAJOR_STEPS if mode == "major" else MINOR_STEPS
    iv = (root - key_root) % 12
    if iv in steps:
        numeral = th.ROMAN[steps.index(iv)]
    elif mode == "major" or iv == 1:
        numeral = "♭" + th.ROMAN[next(i for i, s in enumerate(steps) if s > iv)]
    else:
        numeral = "♯" + th.ROMAN[max(i for i, s in enumerate(steps) if s < iv)]
    if quality in MINORISH:
        numeral = numeral.replace(numeral.lstrip("♭♯"), numeral.lstrip("♭♯").lower())
    return numeral + ROMAN_SUFFIX.get(quality, "")


def is_diatonic(root: int, quality: str, key_root: int, mode: str) -> bool:
    scale = {(key_root + s) % 12 for s in (MAJOR_STEPS if mode == "major" else MINOR_STEPS)}
    return all((root + i) % 12 in scale for i in CHORD_SHAPES[quality])


def job_of(root: int, key_root: int, mode: str) -> str | None:
    steps = MAJOR_STEPS if mode == "major" else MINOR_STEPS
    iv = (root - key_root) % 12
    return JOBS[steps.index(iv)] if iv in steps else None


def fitting_scales(hist: list[float], roots: list[int], key_pcs: set[int], limit: int = 3, need: float = 0.97) -> list[dict]:
    """Scales on the given roots that hold the bar's notes ({root, scale, fit}), the ones inside the key first."""
    total = sum(hist)
    if total <= 0:
        return []
    out = []
    for ri, root in enumerate(dict.fromkeys(roots)):
        for name in FIT_SCALES:
            pcs = {(root + th.INTERVALS[iv][1]) % 12 for iv in th.SCALES[name]}
            fit = sum(hist[p] for p in pcs) / total
            if fit >= need:
                foreign = len(pcs - key_pcs)
                out.append((-round(fit, 3), foreign, ri, len(pcs), dict(root=root, scale=name, fit=round(fit, 2))))
    return [x[-1] for x in sorted(out, key=lambda x: x[:4])][:limit]


def find_progression(labels: list[str | None]) -> dict | None:
    """The run of bars (by chord) that repeats most: cycles of 4 first, then 8 and 2. → {start, length, count}"""
    best = None
    for length, weight in ((4, 1.5), (8, 1.0), (2, 0.8)):
        seen: dict[tuple, dict] = {}
        for i in range(len(labels) - length + 1):
            win = tuple(labels[i:i + length])
            if None in win or len(set(win)) < 2:
                continue
            e = seen.get(win)
            if e is None:
                seen[win] = dict(start=i, count=1, last=i)
            elif i >= e["last"] + length:
                e["count"] += 1
                e["last"] = i
        for e in seen.values():
            rank = e["count"] * length * weight
            if e["count"] >= 2 and (best is None or rank > best["rank"]):
                best = dict(start=e["start"], length=length, count=e["count"], rank=rank)
    return best and {k: best[k] for k in ("start", "length", "count")}


def _resting(notes: list[tuple[float, float, int]]) -> int | None:
    """The bar's resting note: the longest, favoring the downbeat, the middle of the bar and the last note."""
    if not notes:
        return None
    last = max(pos for pos, _, _ in notes)
    def weight(n):
        pos, dur, _ = n
        strong = 1.5 if pos < 0.01 else 1.2 if abs(pos - 0.5) < 0.01 else 1.0
        return dur * strong * (1.3 if pos == last else 1.0)
    return max(notes, key=weight)[2]


KEY_CLOSE = 0.2                                         # keys this close to the best one are weighed by their chords


def _pick_key(keys: list[dict], chords: list[dict | None]) -> tuple[dict, dict]:
    """Key profiles can't tell relative keys apart (G major and E minor share every note). Among the keys close to
    the best one, the winner is the one whose tonic chord sounds most, with a bonus when it opens or closes the song."""
    close = [k for k in keys[:8] if keys[0]["score"] - k["score"] <= KEY_CLOSE]
    present = [c for c in chords if c]

    def tonic(c, k) -> float:                             # how much a chord says "this is home"
        if not c or c["root"] != k["root"] or c["quality"] == "7" or (c["quality"] in MINORISH) != (k["mode"] == "minor"):
            return 0.0                                    # (a dominant 7th points elsewhere)
        return 0.5 if c["quality"] == "m7" else 1.0       # a m7 is often a ii on its way somewhere

    def evidence(k):
        bars = sum(tonic(c, k) for c in present)
        ends = 2 * (tonic(present[0], k) + tonic(present[-1], k)) if present else 0
        blues = 3 if present and present[0]["quality"] == "7" and present[0]["root"] == k["root"] and k["mode"] == "major" else 0
        return bars + ends + blues                        # a blues opens on its I7
    best = max(close, key=lambda k: (evidence(k), k["score"]))
    return best, next(k for k in keys if k is not best)


def analyze(ref: Reference) -> dict:
    """The theory of a reference: key (and the runner-up), chords per bar, usage, progression, bar readings."""
    notes = [n for n in ref.notes if n.end > n.start]
    if not notes:
        return dict(empty=True)
    g = ref.grid
    hist = [0.0] * 12
    bars: dict[int, list] = {}
    for n in notes:
        hist[n.pitch % 12] += n.end - n.start
        bars.setdefault(g.bar_of(n.start)[0], []).append(n)
    # first pass: what each bar sounds like (no key needed yet)
    per_bar = []
    for b in range(min(bars), max(bars) + 1):
        ns = bars.get(b, [])
        h, bass, timed = [0.0] * 12, [0.0] * 12, []
        low = min((n.pitch for n in ns), default=None)
        bpb = g.beats_in_bar(b)
        for n in ns:
            dur = n.end - n.start
            h[n.pitch % 12] += dur
            if low is not None and n.pitch <= low + 4:
                bass[n.pitch % 12] += dur
            timed.append((round((g.bar_of(n.start)[1] - 1) / bpb, 3), dur, n.pitch))
        ch = detect_chord(h, bass)
        per_bar.append((b, ch if ch and ch["fit"] >= 0.6 else None, h, timed))
    keys = estimate_key(hist)
    key, second = _pick_key(keys, [c for _, c, _, _ in per_bar])
    kr, mode = key["root"], key["mode"]
    flats = (kr, mode) in FLAT_KEYS
    key_pcs = {(kr + s) % 12 for s in (MAJOR_STEPS if mode == "major" else MINOR_STEPS)}

    # second pass: the same bars read in that key
    readings, labels, usage = [], [], {}
    diatonic_bars: dict[int, int] = {}                   # bars per root, for the chords of the key
    for b, ch, h, timed in per_bar:
        if ch is None:
            readings.append(dict(bar=b, chord=None))
            labels.append(None)
            continue
        name = _name(ch["root"], flats) + SUFFIX[ch["quality"]]
        rest = _resting(timed)
        reading = dict(bar=b, chord=name, roman=roman_of(ch["root"], ch["quality"], kr, mode),
                       diatonic=is_diatonic(ch["root"], ch["quality"], kr, mode),
                       fit=ch["fit"], resting=None if rest is None else dict(note=_name(rest, flats),
                       degree=th.DEGREE.get(th.BY_SEMITONES[(rest - ch["root"]) % 12], "?")),
                       scales=[dict(s, root=_name(s["root"], flats)) for s in fitting_scales(h, [ch["root"], kr], key_pcs)])
        reading["job"] = job_of(ch["root"], kr, mode) if reading["diatonic"] else None   # only chords of the key have a job
        readings.append(reading)
        labels.append(name)
        u = usage.setdefault(name, dict(chord=name, roman=reading["roman"], diatonic=reading["diatonic"], job=reading["job"], bars=0))
        u["bars"] += 1
        if reading["diatonic"]:
            diatonic_bars[ch["root"]] = diatonic_bars.get(ch["root"], 0) + 1
    prog = find_progression(labels)
    if prog:
        seq = readings[prog["start"]:prog["start"] + prog["length"]]
        prog.update(chords=[r["chord"] for r in seq], romans=[r["roman"] for r in seq], bar=seq[0]["bar"])
    hz = th.harmonize(_name(kr, flats), "major" if mode == "major" else "natural_minor")
    field = [dict(roman=c["roman"], chord=c["symbol"], job=JOBS[c["degree"] - 1],
                  bars=diatonic_bars.get(th.pc(c["notes"][0]), 0)) for c in hz]
    usage_sorted = sorted(usage.values(), key=lambda u: -u["bars"])
    return dict(key=dict(root=_name(kr, flats), mode=mode, score=round(key["score"], 2)),
                second=dict(root=_name(second["root"], (second["root"], second["mode"]) in FLAT_KEYS), mode=second["mode"],
                            score=round(second["score"], 2)),
                field=field, usage=usage_sorted, outside=[u for u in usage_sorted if not u["diatonic"]],
                progression=prog, bars=readings)
