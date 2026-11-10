"""Learning content: chord dictionary, chord charts and the course.

- guitarr/data/chords.json   : fingerings (6th→1st string, -1 = not played)
- guitarr/data/charts/*.txt  : built-in exercises, in the text format below
- ~/.guitarr/charts/*.txt    : your own charts
- guitarr/data/course.json   : levels → lessons → exercises you pass by playing

Lick tabs (course exercises of kind "lick") are space-separated tokens, "string:fret"
followed by what the fretting hand does next, as in written tab:

    3:5h7   hammer-on to fret 7      3:7p5   pull-off to fret 5
    3:5/7   slide up to fret 7       3:7\\5   slide down to fret 5
    3:7b9   bend up to fret 9's pitch (the picked fret 7 isn't a note of its own)
    3:7b9r7 bend and release         2:5~    vibrato (doesn't change the notes)

Chart format (plain text):

    title: Pop in G
    bpm: 90
    time: 4/4            # optional (4/4)
    capo: 2              # optional
    strum: D.DU.UDU      # optional: D down, U up, . rest, _ hold (tie), ^ next chord early (anticipation)
    swing: light         # optional: light, medium, hard or a ratio 0.5–0.75 (offbeat eighths come later)
    voicing: shell       # optional: shell, drop2, drop3 or triad voices every chord (any chord symbol)
    level: 2             # optional (built-in charts take it from the lesson that uses them)
    note: a tip          # optional

    [Verse]
    G | D | Em | C       # one bar per cell; "C G" = two chords in one bar
    G | % | Em | -       # % repeats the previous chord, - is a silent bar
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import config

DATA_DIR = Path(__file__).parent / "data"
OPEN_STRINGS = [40, 45, 50, 55, 59, 64]  # 6th ... 1st
HEADER_KEYS = {"title", "artist", "level", "bpm", "time", "capo", "strum", "note", "voicing", "swing", "tuning"}


class CatalogError(Exception):
    pass


# ---------------------------------------------------------------- chords
@lru_cache(maxsize=None)
def _chords_data() -> dict:
    return json.loads((DATA_DIR / "chords.json").read_text(encoding="utf-8"))


def chord_groups() -> list[dict]:
    return _chords_data()["groups"]


@lru_cache(maxsize=None)
def chords() -> list[dict]:
    """The chord library. A chord is in its quality group (major, minor, sevenths...) and also in "barre" when it is
    played with a barre, so F shows up with the major chords and with the barre chords. `level` and `lesson` say where
    the course teaches it (None if no lesson does)."""
    taught = taught_at()["chords"]
    out = []
    for c in _chords_data()["chords"]:
        level, lesson, title = taught.get(c["id"], (None, None, None))
        out.append({**c, "groups": [c["group"]] + (["barre"] if c.get("barre") else []), "level": level, "lesson": lesson,
                    "lesson_title": title})
    return out


@lru_cache(maxsize=None)
def taught_at() -> dict:
    """Where the course first teaches each chord (a lesson's "chords") and first uses each built-in chart: the course
    is the one source of truth for levels, so reordering levels never leaves a chord or a chart behind."""
    chords_at, charts_at = {}, {}
    for lvl in all_levels():
        for ls in lvl["lessons"]:
            for c in ls.get("chords") or []:
                chords_at.setdefault(c, (lvl["number"], ls["id"], ls["title"]))
            for ex in ls["exercises"]:
                if ex["kind"] == "chart":
                    charts_at.setdefault(ex["chart"], lvl["number"])
    return dict(chords=chords_at, charts=charts_at)


def get_chord(cid: str) -> dict | None:
    return next((c for c in chords() if c["id"] == cid), None)


def chord_pitches(chord: dict, capo: int = 0) -> list[int]:
    return [OPEN_STRINGS[i] + capo + f for i, f in enumerate(chord["frets"]) if f is not None and f >= 0]


# ---------------------------------------------------------------- charts
def user_dir() -> Path:
    return config.HOME / "charts"


def slug(text: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return s[:60] or "chart"


def parse_chart(text: str, cid: str = "chart") -> dict:
    """Text → chart (dict). Errors mention the line number."""
    meta: dict = {}
    bars: list[dict] = []
    section = None
    prev = None
    unknown: list[str] = []
    for ln, raw in enumerate(text.splitlines(), start=1):
        # "#" starts a comment at the beginning of a line or after a space; inside a chord (C#m7) it's a sharp
        line = "" if raw.lstrip().startswith("#") else re.split(r"\s#(?:\s|$)", raw, maxsplit=1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([a-z]+)\s*:\s*(.*)$", line, re.I)
        if m and m.group(1).lower() in HEADER_KEYS and "|" not in line:
            meta[m.group(1).lower()] = m.group(2).strip()
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1).strip()
            continue
        bpb = _beats_per_bar(meta.get("time", "4/4"), ln)
        for cell in [c.strip() for c in line.split("|")]:
            if not cell:
                continue
            names = cell.split()
            per = bpb / len(names)
            for name in names:
                if name == "%":
                    if prev is None:
                        raise CatalogError(f"Line {ln}: '%' with no chord before it")
                    name = prev
                if name in ("-", "NC", "N.C."):
                    bars.append(dict(chord=None, beats=per, frets=[], section=section))
                else:
                    ch = get_chord(name)
                    if ch is None and name not in unknown:
                        unknown.append(name)
                    bars.append(dict(chord=name, beats=per, frets=ch["frets"] if ch else [], section=section))
                    prev = name
                section = None
    if not bars:
        raise CatalogError("The chart has no bars (lines with chords separated by |).")
    try:
        bpm = float(meta.get("bpm", 90))
        capo = int(meta.get("capo", 0) or 0)
        level = int(meta.get("level", 0) or 0)
    except ValueError as e:
        raise CatalogError(f"Invalid header: {e}") from e
    if not 20 <= bpm <= 300:
        raise CatalogError("bpm must be between 20 and 300")
    voicing = meta.get("voicing", "").lower()
    if voicing:
        unknown = _voice_chart(bars, voicing)
    return dict(id=cid, title=meta.get("title") or cid, artist=meta.get("artist"), bpm=bpm,
                beats_per_bar=_beats_per_bar(meta.get("time", "4/4"), 0), capo=capo, level=level,
                strum=meta.get("strum", ""), note=meta.get("note", ""), bars=bars, missing=unknown,
                swing=_swing(meta.get("swing", "")), voicing=voicing or None, tuning=_tuning(meta.get("tuning", "")))


SWING = {"": 0.0, "straight": 0.0, "off": 0.0, "light": 0.6, "medium": 0.64, "hard": 0.67}


def _tuning(v: str) -> str:
    """`tuning: drop_d` (any tuning the app knows); empty = standard."""
    from .core import TUNINGS

    v = (v or "standard").strip().lower().replace(" ", "_").replace("-", "_")
    if v not in TUNINGS:
        raise CatalogError(f"tuning: one of {', '.join(TUNINGS)} (not '{v}')")
    return v


def _swing(v: str) -> float:
    """Where the offbeat eighth falls inside the beat: 0 = straight (0.5), light 0.6, hard 0.67 (triplet feel)."""
    v = v.strip().lower()
    if v in SWING:
        return SWING[v]
    try:
        r = float(v)
    except ValueError as e:
        raise CatalogError(f"swing: write light, medium, hard or a number between 0.5 and 0.75 (not '{v}')") from e
    if not 0.5 <= r <= 0.75:
        raise CatalogError("swing must be between 0.5 and 0.75")
    return 0.0 if r == 0.5 else r


def _voice_chart(bars: list[dict], voicing: str) -> list[str]:
    """`voicing: shell|drop2|drop3|triad` voices every chord with the theory engine, each one close to the last
    (so jazz charts don't depend on the chord dictionary). Returns the chords it couldn't voice."""
    from . import theory as th

    names = [b["chord"] for b in bars if b["chord"]]
    seq = [n for i, n in enumerate(names) if i == 0 or n != names[i - 1]]
    bad = []
    for n in dict.fromkeys(seq):
        try:
            th.voicings(n, voicing)
        except (th.TheoryError, KeyError):
            bad.append(n)
    if bad:
        return bad
    shapes = th.voice_lead(seq, voicing, "smooth", start=3)
    it = iter(shapes)
    cur, last = None, None
    for b in bars:
        if not b["chord"]:
            continue
        if b["chord"] != last:
            cur = next(it)["frets"]
            last = b["chord"]
        b["frets"] = cur
    return []


def _beats_per_bar(sig: str, ln: int) -> int:
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", sig or "4/4")
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise CatalogError(f"Line {ln}: invalid time signature '{sig}' (e.g. 4/4, 3/4, 6/8)")
    return int(m.group(1))


def _chart_files() -> dict[str, tuple[Path, bool]]:
    out = {p.stem: (p, False) for p in sorted((DATA_DIR / "charts").glob("*.txt"))}
    if user_dir().exists():
        out.update({p.stem: (p, True) for p in sorted(user_dir().glob("*.txt"))})
    return out


def charts() -> list[dict]:
    rows = []
    for cid, (p, mine) in _chart_files().items():
        try:
            c = parse_chart(p.read_text(encoding="utf-8"), cid)
        except CatalogError as e:
            rows.append(dict(id=cid, title=cid, mine=mine, error=str(e)))
            continue
        chords_used = list(dict.fromkeys(b["chord"] for b in c["bars"] if b["chord"]))
        level = c["level"] if mine else taught_at()["charts"].get(cid, c["level"])     # built-in: the course decides
        rows.append(dict(id=cid, title=c["title"], artist=c["artist"], level=level, bpm=c["bpm"],
                         capo=c["capo"], beats_per_bar=c["beats_per_bar"], strum=c["strum"], note=c["note"],
                         chords=chords_used, bars=len(c["bars"]), missing=c["missing"], mine=mine, tuning=c["tuning"]))
    rows.sort(key=lambda r: (r.get("mine", False), r.get("level") or 0, r["id"]))
    return rows


def chart_text(cid: str) -> tuple[str, bool]:
    f = _chart_files().get(cid)
    if f is None:
        raise CatalogError(f"Chart '{cid}' not found (see: guitarr charts)")
    return f[0].read_text(encoding="utf-8"), f[1]


def get_chart(cid: str) -> dict:
    text, _ = chart_text(cid)
    return parse_chart(text, cid)


def save_chart(text: str, cid: str | None = None) -> dict:
    c = parse_chart(text, cid or "new")
    if c["missing"]:
        raise CatalogError(f"Unknown chords: {', '.join(c['missing'])} (see the chord dictionary)")
    cid = cid or slug(c["title"])
    builtin = (DATA_DIR / "charts" / f"{cid}.txt").exists()
    if builtin:
        cid = f"{cid}-mine"
    user_dir().mkdir(parents=True, exist_ok=True)
    (user_dir() / f"{cid}.txt").write_text(text.strip() + "\n", encoding="utf-8")
    return dict(id=cid, title=c["title"])


def delete_chart(cid: str) -> None:
    f = _chart_files().get(cid)
    if f is None or not f[1]:
        raise CatalogError("Only your own charts can be deleted.")
    f[0].unlink()


def chart_from_chord(cid: str, times: int = 1) -> dict:
    ch = get_chord(cid)
    if ch is None:
        raise CatalogError(f"Unknown chord '{cid}'")
    return dict(id=f"chord-{cid}", title=ch["id"], bpm=60, beats_per_bar=1, capo=0,
                bars=[dict(chord=cid, beats=1, frets=ch["frets"]) for _ in range(times)])


def chart_alternating(names: list[str], times: int) -> dict:
    bars = []
    for _ in range(times):
        for n in names:
            ch = get_chord(n)
            if ch is None:
                raise CatalogError(f"Unknown chord '{n}'")
            bars.append(dict(chord=n, beats=1, frets=ch["frets"]))
    return dict(id="change-" + "-".join(names), title=" ↔ ".join(names), bpm=60, beats_per_bar=1, capo=0, bars=bars)


# ---------------------------------------------------------------- licks and bends
_TOKEN = re.compile(r"^([1-6]):(\d+)((?:[hpbr/\\]\d+|~)*)$")
_OP = re.compile(r"([hpbr/\\])(\d+)|~")
TECH = {"h": "hammer", "p": "pull", "/": "slide", "\\": "slide", "b": "bend", "r": "release"}


def _pitch(string: int, fret: int) -> int:
    return OPEN_STRINGS[6 - string] + fret


def _shift_token(string: int, frets: list[int], shift: int) -> list[int]:
    """Moves a token's frets by `shift` semitones, an octave up or down if it falls off the neck."""
    out = [f + shift for f in frets]
    if min(out) < 0:
        out = [f + 12 for f in out]
    elif max(out) > 20:
        out = [f - 12 for f in out]
    return out


_PART = re.compile(r"^([1-6]):(\d+)(~?)$")


def _together(tok: str, shift: int) -> list[dict]:
    """'6:3+1:3': notes picked at the same time (a pinch, a double stop). The first one is the
    step; the others carry together=True. Plain notes only (a ~ is fine)."""
    parts = [_PART.match(x) for x in tok.split("+")]
    if not all(parts):
        raise CatalogError(f"Lick: can't read '{tok}' (notes together are plain, e.g. 6:3+1:3 or 3:7+2:8~)")
    strings = [int(m.group(1)) for m in parts]
    if len(set(strings)) != len(strings):
        raise CatalogError(f"Lick: '{tok}' plays one string twice")
    frets = _shift_token(0, [int(m.group(2)) for m in parts], shift)
    return [dict(string=st, fret=f, pitch=_pitch(st, f), tech="pick", glide_from=None, vibrato=bool(m.group(3)),
                 **(dict(together=True) if k else {}))
            for k, (st, f, m) in enumerate(zip(strings, frets, parts))]


def parse_lick(tab: str, shift: int = 0) -> list[dict]:
    """Lick tab → steps (string, fret, pitch, tech, glide_from, vibrato). Errors name the token.
    Notes joined with + sound together: the extra ones carry together=True."""
    steps: list[dict] = []
    for tok in tab.split():
        if "+" in tok:
            steps += _together(tok, shift)
            continue
        m = _TOKEN.match(tok)
        if not m:
            raise CatalogError(f"Lick: can't read '{tok}' (e.g. 3:5, 3:5h7, 3:7b9r7, 2:5~, 6:3+1:3)")
        string = int(m.group(1))
        ops = [(o.group(1), int(o.group(2))) if o.group(1) else ("~", None) for o in _OP.finditer(m.group(3))]
        frets = _shift_token(string, [int(m.group(2))] + [f for op, f in ops if f is not None], shift)
        fi = iter(frets)
        fret = next(fi)
        cur = _pitch(string, fret)
        if not ops or ops[0][0] != "b":
            steps.append(dict(string=string, fret=fret, pitch=cur, tech="pick", glide_from=None, vibrato=False))
        for op, _ in ops:
            if op == "~":
                if steps:
                    steps[-1]["vibrato"] = True
                continue
            to = next(fi)
            p = _pitch(string, to)
            if op == "b" and p <= cur:
                raise CatalogError(f"Lick: '{tok}' bends down")
            glide = cur if op in ("b", "r", "/", "\\") else None
            # a bend is still fretted where you picked it; everything else moves the finger
            shown = fret if op == "b" else to
            steps.append(dict(string=string, fret=shown, pitch=p, tech=TECH[op], glide_from=glide, vibrato=False))
            cur = p
            if op != "b":
                fret = to
    if not steps:
        raise CatalogError("Lick: no notes")
    return steps


def bend_steps(ex: dict) -> list[dict]:
    """A bend exercise: the same bend, once per try."""
    s, f, up = int(ex["string"]), int(ex["fret"]), int(ex.get("bend", 2))
    if not 1 <= up <= 3:
        raise CatalogError("A bend goes up 1 to 3 semitones")
    one = dict(string=s, fret=f, pitch=_pitch(s, f) + up, tech="bend", glide_from=_pitch(s, f), vibrato=False)
    return [dict(one) for _ in range(int(ex.get("tries", 10)))]


def exercise_steps(ex: dict) -> list[dict] | None:
    """Tab steps of a lick, bend, scale, arpeggio or guide-tone line exercise (None for other kinds)."""
    if ex["kind"] == "lick":
        return parse_lick(ex["tab"], int(ex.get("shift", 0)))
    if ex["kind"] == "bend":
        return bend_steps(ex)
    if ex["kind"] in RUN_KINDS:
        return [dict(string=s, fret=f, pitch=p, tech="pick", glide_from=None, vibrato=False) for s, f, p in _run(ex)]
    return None


# kinds you play: scale/arpeggio/line runs and chord shapes are built by the theory engine
RUN_KINDS = ("scale", "arpeggio", "line", "caged")
ANSWER_KINDS = ("quiz", "pick", "tap")          # passed by answering (or tapping), not by the listener
SHAPE_KINDS = ("shape", "voiced")


def _run(ex: dict) -> list[tuple[int, int, int]]:
    from . import theory as th

    lo, hi = (ex.get("frets") or [0, 12])
    try:
        if ex["kind"] == "scale":
            return th.scale_path(ex["key"], ex["scale"], lo, hi, ex.get("direction", "up"), ex.get("string"),
                                 int(ex.get("nps", 0)), int(ex.get("octaves", 1)))
        if ex["kind"] == "arpeggio":
            return th.arpeggio_path(ex["chord"], lo, hi, ex.get("direction", "up"), int(ex.get("octaves", 1)))
        if ex["kind"] == "caged":                       # one shape, or several in a row up the neck
            ch = th.parse_chord(ex["chord"])
            shapes = th.caged_along(ch["root"], ch["quality"], ex.get("caged", "CAGED"))
            run = []
            for c in shapes:
                path = c["path"] + c["path"][-2::-1] if ex.get("direction") == "updown" else c["path"]
                run += path
            if not run:
                raise th.TheoryError("no shape fits")
            return run
        style = ex.get("style", "guide")
        if style == "guide":
            return th.guide_line(ex["progression"], lo, hi, int(ex.get("per_chord", 1)))
        return th.jazz_line(ex["progression"], style, lo, hi, str(ex.get("start", "3")), ex.get("direction", "up"))
    except (th.TheoryError, StopIteration) as e:
        raise CatalogError(f"Can't build {ex['kind']} '{ex.get('id')}': {e}") from e


def exercise_shapes(ex: dict) -> list[dict] | None:
    """[{name, frets}] for chord-shape exercises: one shape, or a voiced progression (None for other kinds)."""
    from . import theory as th

    if ex["kind"] not in SHAPE_KINDS:
        return None
    try:
        if ex.get("shapes"):                                   # written out by hand
            return [dict(name=s["name"], frets=list(s["frets"])) for s in ex["shapes"]]
        if ex["kind"] == "shape":
            near = int(ex.get("near", 3))
            all_v = th.voicings(ex["chord"], ex["voicing"])
            out = []
            for inv in ex.get("inversions", [ex.get("inversion")]):
                vs = [v for v in all_v if v["strings"] == ex.get("strings", v["strings"]) and (inv is None or v["inversion"] == int(inv))]
                if not vs:
                    raise th.TheoryError(f"no {ex['voicing']} of {ex['chord']} on {ex.get('strings')}")
                v = min(vs, key=lambda v: (abs(v["position"] - near), v["position"]))
                name = ex["chord"]
                if ex.get("inversions") and v["inversion"]:          # several inversions: name each by its bass
                    c = th.chord(ex["chord"])
                    name += "/" + th.tone(c, v["order"][0])["note"]
                out.append(dict(name=name, frets=v["frets"]))
            return out
        prog = ex["progression"]
        if ex["voicing"] == "guide":
            shapes = th.guide_tones(prog, tuple(ex.get("strings", (4, 3))))
        else:
            sets = tuple(ex["sets"]) if ex.get("sets") else None
            shapes = th.voice_lead(prog, ex["voicing"], ex.get("lead", "smooth"), int(ex.get("near", 3)), sets)
        return [dict(name=s["name"], frets=s["frets"]) for s in shapes]
    except (th.TheoryError, ValueError) as e:
        raise CatalogError(f"Can't build shapes for '{ex.get('id')}': {e}") from e


def chart_from_shapes(shapes: list[dict], times: int) -> dict:
    """Each shape once per round, one beat each (graded like a chord change)."""
    bars = [dict(chord=s["name"], beats=1, frets=s["frets"]) for _ in range(times) for s in shapes]
    return dict(id="shapes-" + "-".join(s["name"] for s in shapes), title=" → ".join(s["name"] for s in shapes),
                bpm=60, beats_per_bar=1, capo=0, bars=bars)


# ---------------------------------------------------------------- course
@lru_cache(maxsize=None)
def course() -> dict:
    data = json.loads((DATA_DIR / "course.json").read_text(encoding="utf-8"))
    data.setdefault("optional", [])
    for lvl in data["levels"] + data["optional"]:
        recap = _recap(lvl)
        if recap:
            lvl["lessons"].append(recap)
        for ls in lvl["lessons"]:            # a suggested rig sound: the lesson's own, else its level's
            if lvl.get("tone"):
                ls.setdefault("tone", lvl["tone"])
    return data


RECAP_MIN_LESSONS = 3
RECAP_MAX = 8


def _recap(lvl: dict) -> dict | None:
    """The last lesson of a level: a mixed review with one exercise from each lesson (a quiz when the lesson has
    one, so you check you understood; otherwise the last thing you played). Generated, so it never goes stale."""
    src = [ls for ls in lvl["lessons"] if not ls.get("recap")]
    if len(src) < RECAP_MIN_LESSONS:
        return None
    picks = []
    for ls in src:
        exs = ls["exercises"]
        ex = next((e for e in exs if e["kind"] in ANSWER_KINDS), None) or exs[-1]
        picks.append({**ex, "id": f"{ls['id']}--{ex['id']}", "from": f"{ls['id']}/{ex['id']}"})
    if len(picks) > RECAP_MAX:                       # spread the picks over the whole level
        step = len(picks) / RECAP_MAX
        picks = [picks[int(i * step)] for i in range(RECAP_MAX)]
    return dict(id=f"recap-{lvl['id']}", title=f"Level {lvl.get('badge') or lvl['number']} recap", minutes=5 + 3 * len(picks), recap=True,
                theory=[], tips=[], tutorials=[], exercises=picks)


# the five steps of a lesson: discover → understand → guided practice → independent practice → vary and apply
STAGES = ("discover", "understand", "guided", "independent", "apply")
FADEABLE = ("lick", "scale", "arpeggio", "line", "shape", "voiced", "notes", "caged")


def exercise_stage(ex: dict) -> str:
    """Which step of the lesson an exercise belongs to (an explicit "stage" in course.json wins)."""
    if ex.get("stage") in STAGES:
        return ex["stage"]
    if ex["kind"] in ANSWER_KINDS:
        return "understand"
    if ex["kind"] == "chart":
        return "apply"
    return "guided"


def _shift_window(frets, by: int) -> list[int]:
    lo, hi = frets or [0, 12]
    if hi + by > 15:
        by -= 12
    if lo + by < 0:
        by += 12
    return [lo + by, hi + by]


def _transpose_symbol(sym: str, interval: str) -> str:
    from . import theory as th

    c = th.parse_chord(sym)
    root = th.transpose(c["root"], interval)
    bass = th.transpose(c["bass"], interval) if c["bass"] else None
    return th.chord_symbol(_simple(root), c["quality"], _simple(bass) if bass else None)


def _simple(note: str) -> str:
    """Double sharps/flats read badly in a chord symbol: E## → F#, Cbb → Bb."""
    from . import theory as th

    letter, acc = th.parse_note(note)
    return th.plain_name(th.pc(note)) if abs(acc) > 1 else note


def variation(ex: dict) -> dict | None:
    """The same exercise a 4th higher (another key, another position), or None when it can't move.
    Checks that you learned the relationship, not a picture."""
    from . import theory as th

    k = ex["kind"]
    try:
        if k == "scale":
            key = _simple(th.transpose(ex["key"], "P4"))
            return {**ex, "key": key, "frets": _shift_window(ex.get("frets"), 5), "_label": dict(code="in_key", key=key)}
        if k == "arpeggio":
            ch = _transpose_symbol(ex["chord"], "P4")
            return {**ex, "chord": ch, "frets": _shift_window(ex.get("frets"), 5), "_label": dict(code="over", chords=ch)}
        if k == "caged":                                # the same shapes of another chord
            ch = _transpose_symbol(ex["chord"], "P4")
            return {**ex, "chord": ch, "_label": dict(code="over", chords=ch)}
        if k in ("line", "voiced") and ex.get("progression"):
            prog = [_transpose_symbol(s, "P4") for s in ex["progression"]]
            out = {**ex, "progression": prog, "_label": dict(code="over", chords=" → ".join(prog))}
            if ex.get("frets"):
                out["frets"] = _shift_window(ex["frets"], 5)
            if k == "voiced":
                out["near"] = (int(ex.get("near", 3)) + 5) % 12
            return out
        if k == "shape" and ex.get("chord"):
            ch = _transpose_symbol(ex["chord"], "P4")
            return {**ex, "chord": ch, "near": (int(ex.get("near", 3)) + 5) % 12, "_label": dict(code="over", chords=ch)}
        if k == "lick":
            frets = [int(f) for f in re.findall(r":(\d+)", ex["tab"])]
            by = -2 if min(frets) >= 2 else 2
            return {**ex, "shift": int(ex.get("shift", 0)) + by, "_label": dict(code="moved", frets=by)}
    except (th.TheoryError, KeyError, ValueError):
        return None
    return None


def chart_sections(chart: dict) -> list[dict]:
    """[{name, from, to}] — each section of a chart with its bar numbers (bars counted in beats per bar)."""
    bpb, acc, out = chart["beats_per_bar"], 0.0, []
    for b in chart["bars"]:
        bar = int(acc // bpb) + 1
        if b.get("section"):
            if out:
                out[-1]["to"] = max(out[-1]["from"], bar - 1)
            out.append(dict(name=b["section"], **{"from": bar, "to": bar}))
        acc += b["beats"]
    if out:
        out[-1]["to"] = max(out[-1]["from"], int((acc - 1e-6) // bpb) + 1)
    # sections with the same name (A, A) get a number so each one is its own row
    seen: dict[str, int] = {}
    for s in out:
        seen[s["name"]] = seen.get(s["name"], 0) + 1
        s["key"] = s["name"] if seen[s["name"]] == 1 else f"{s['name']} ({seen[s['name']]})"
    return out


def lessons() -> list[dict]:
    """The main course, in order (what progress, the plan and "next lesson" count)."""
    return [ls for lvl in course()["levels"] for ls in lvl["lessons"]]


def all_levels() -> list[dict]:
    """The main course, then the optional courses (each optional level has a "track", like "metal")."""
    return course()["levels"] + course()["optional"]


def all_lessons() -> list[dict]:
    return [ls for lvl in all_levels() for ls in lvl["lessons"]]


def track_lessons(lid: str) -> list[dict]:
    """The lessons of the course (main or one optional track) that `lid` belongs to, in order."""
    for group in [course()["levels"]] + [[lv for lv in course()["optional"] if lv.get("track") == t]
                                         for t in dict.fromkeys(lv.get("track") for lv in course()["optional"])]:
        out = [ls for lvl in group for ls in lvl["lessons"]]
        if any(ls["id"] == lid for ls in out):
            return out
    return lessons()


def lesson_chords(ls: dict) -> list[str]:
    """The lesson's own chords, then every chord its exercises use (charts included), each once."""
    out = list(ls.get("chords") or [])
    for ex in ls["exercises"]:
        if ex["kind"] == "chord":
            out.append(ex["chord"])
        elif ex["kind"] == "change":
            out += ex["chords"]
        elif ex["kind"] == "chart":
            out += [b["chord"] for b in get_chart(ex["chart"])["bars"] if b["chord"]]
    return [c for c in dict.fromkeys(out) if get_chord(c)]


def get_lesson(lid: str) -> dict:
    ls = next((x for x in all_lessons() if x["id"] == lid), None)
    if ls is None:
        raise CatalogError(f"Lesson '{lid}' not found")
    return ls


def get_exercise(lid: str, eid: str) -> dict:
    ex = next((e for e in get_lesson(lid)["exercises"] if e["id"] == eid), None)
    if ex is None:
        raise CatalogError(f"Exercise '{eid}' not found in '{lid}'")
    return ex


def exercise_setup(lid: str, eid: str, variant: bool = False):
    """→ (RefOptions, mode, speed, minimum score) to listen to an exercise (or to its variation)."""
    from .reference import RefOptions

    ex = get_exercise(lid, eid)
    if variant:
        from . import quiz
        ex = quiz.variant_of(lid, ex)
    kind = ex["kind"]
    if kind == "notes":
        return RefOptions(notes=list(ex["notes"])), "wait", 1.0, ex.get("min", 80)
    if kind == "chord":
        return RefOptions(chart=chart_from_chord(ex["chord"], ex.get("times", 4))), "wait", 1.0, ex.get("min", 75)
    if kind == "change":
        return RefOptions(chart=chart_alternating(ex["chords"], ex.get("times", 4))), "wait", 1.0, ex.get("min", 75)
    if kind == "chart":
        return RefOptions(chart=get_chart(ex["chart"])), "tempo", ex.get("speed", 1.0), ex.get("min", 80)
    if kind == "lick":
        return RefOptions(tab=exercise_steps(ex)), "wait", 1.0, ex.get("min", 80)
    if kind == "bend":
        return RefOptions(tab=exercise_steps(ex)), "bend", 1.0, ex.get("min", 70)
    if kind in RUN_KINDS:
        return RefOptions(tab=exercise_steps(ex)), "wait", 1.0, ex.get("min", 80)
    if kind in SHAPE_KINDS:
        return RefOptions(chart=chart_from_shapes(exercise_shapes(ex), int(ex.get("times", 2)))), "wait", 1.0, ex.get("min", 75)
    if kind in ("find_note", "play_interval", "tone_row", "read_play"):
        from . import quiz
        return RefOptions(notes=quiz.drawn_notes(lid, ex)), "wait", 1.0, ex.get("min", 80)
    if kind in ("echo", "rhythm"):                      # pitches and rhythm: played on the metronome
        from . import quiz
        return RefOptions(timed=quiz.drawn_timed(lid, ex), bpm=float(ex.get("bpm", 80))), "tempo", 1.0, ex.get("min", 75)
    raise CatalogError(f"Unknown exercise kind: {kind}")


# ---------------------------------------------------------------- terminal
def print_charts(cid: str | None = None) -> None:
    if cid is None:
        print("Charts (play one with: guitarr live --chart ID --mode tempo):\n")
        for c in charts():
            if c.get("error"):
                print(f"  {c['id']:26s} ⚠️  {c['error']}")
                continue
            tag = "  (yours)" if c["mine"] else ""
            capo = f" capo {c['capo']}" if c["capo"] else ""
            print(f"  {c['id']:26s} {c['title']}  ♩={c['bpm']:g}{capo}  [{' '.join(c['chords'])}]{tag}")
        print(f"\nYour charts live in {user_dir()} (format: `guitarr charts --format`)")
        return
    c = get_chart(cid)
    print(f"{c['title']}  ♩={c['bpm']:g}  {c['beats_per_bar']}/4" + (f"  capo {c['capo']}" if c["capo"] else "")
          + (f"  strum {c['strum']}" if c["strum"] else ""))
    if c["note"]:
        print(f"  {c['note']}")
    line: list[str] = []
    acc = 0.0
    for b in c["bars"]:
        if b.get("section"):
            if line:
                print("  " + " | ".join(line))
                line = []
            print(f"\n[{b['section']}]")
        name = b["chord"] or "-"
        if acc and line:
            line[-1] += f" {name}"
        else:
            line.append(name)
        acc = (acc + b["beats"]) % c["beats_per_bar"]
    if line:
        print("  " + " | ".join(line))


# ---------------------------------------------------------------- what to do next, and why
def next_step(lid: str, eid: str, award: dict, prog: dict) -> dict:
    """After a take or a quiz: one suggestion as {code, params} (the UI says it in any language)."""
    ls = get_lesson(lid)
    ex = next(e for e in ls["exercises"] if e["id"] == eid)
    key = f"{lid}/{eid}"
    score, need = award.get("score"), award.get("need", ex.get("min", 80))
    if award.get("variant"):
        return dict(code="variant_done" if award.get("passed") else "variant_retry")
    if not award.get("passed"):
        if score is None:
            return dict(code="not_heard")
        if ex["kind"] in ANSWER_KINDS:
            return dict(code="quiz_retry", params=dict(need=need))
        if score < 50:
            return dict(code="retry_slower" if ex["kind"] == "chart" else "retry_with_help")
        return dict(code="almost", params=dict(missing=round(need - score)))
    if award.get("lesson_done"):
        lessons_ = track_lessons(lid)
        i = next(k for k, x in enumerate(lessons_) if x["id"] == lid)
        nxt = lessons_[i + 1] if i + 1 < len(lessons_) else None
        return dict(code="next_lesson", params=dict(lesson=nxt["id"], title=nxt["title"])) if nxt else dict(code="all_done")
    if ex["kind"] in FADEABLE and (prog["guidance"].get(key) or 0) < 2:
        return dict(code="less_help", params=dict(level=(prog["guidance"].get(key) or 0) + 1))
    if variation(ex) is not None and prog["variations"].get(key, -1) < need:
        return dict(code="try_variation")
    after = next((e for e in ls["exercises"] if prog["exercises"].get(f"{lid}/{e['id']}", -1) < e.get("min", 80)), None)
    if after:
        return dict(code="next_exercise", params=dict(exercise=after["id"], title=after["title"]))
    return dict(code="lesson_review")
