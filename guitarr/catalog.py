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
    strum: D.DU.UDU      # optional: D down, U up, . rest (one slot per eighth note)
    level: 2             # optional
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
HEADER_KEYS = {"title", "artist", "level", "bpm", "time", "capo", "strum", "note"}


class CatalogError(Exception):
    pass


# ---------------------------------------------------------------- chords
@lru_cache(maxsize=None)
def _chords_data() -> dict:
    return json.loads((DATA_DIR / "chords.json").read_text(encoding="utf-8"))


def chord_groups() -> list[dict]:
    return _chords_data()["groups"]


def chords() -> list[dict]:
    return _chords_data()["chords"]


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
        line = raw.split("#", 1)[0].strip()
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
    return dict(id=cid, title=meta.get("title") or cid, artist=meta.get("artist"), bpm=bpm,
                beats_per_bar=_beats_per_bar(meta.get("time", "4/4"), 0), capo=capo, level=level,
                strum=meta.get("strum", ""), note=meta.get("note", ""), bars=bars, missing=unknown)


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
        rows.append(dict(id=cid, title=c["title"], artist=c["artist"], level=c["level"], bpm=c["bpm"],
                         capo=c["capo"], beats_per_bar=c["beats_per_bar"], strum=c["strum"], note=c["note"],
                         chords=chords_used, bars=len(c["bars"]), missing=c["missing"], mine=mine))
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


def parse_lick(tab: str, shift: int = 0) -> list[dict]:
    """Lick tab → steps (string, fret, pitch, tech, glide_from, vibrato). Errors name the token."""
    steps: list[dict] = []
    for tok in tab.split():
        m = _TOKEN.match(tok)
        if not m:
            raise CatalogError(f"Lick: can't read '{tok}' (e.g. 3:5, 3:5h7, 3:7b9r7, 2:5~)")
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
    if ex["kind"] in ("scale", "arpeggio", "line"):
        return [dict(string=s, fret=f, pitch=p, tech="pick", glide_from=None, vibrato=False) for s, f, p in _run(ex)]
    return None


# kinds you play: scale/arpeggio/line runs and chord shapes are built by the theory engine
RUN_KINDS = ("scale", "arpeggio", "line")
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
        return th.guide_line(ex["progression"], lo, hi, int(ex.get("per_chord", 1)))
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
    return json.loads((DATA_DIR / "course.json").read_text(encoding="utf-8"))


def lessons() -> list[dict]:
    return [ls for lvl in course()["levels"] for ls in lvl["lessons"]]


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
    ls = next((x for x in lessons() if x["id"] == lid), None)
    if ls is None:
        raise CatalogError(f"Lesson '{lid}' not found")
    return ls


def get_exercise(lid: str, eid: str) -> dict:
    ex = next((e for e in get_lesson(lid)["exercises"] if e["id"] == eid), None)
    if ex is None:
        raise CatalogError(f"Exercise '{eid}' not found in '{lid}'")
    return ex


def exercise_setup(lid: str, eid: str):
    """→ (RefOptions, mode, speed, minimum score) to listen to an exercise."""
    from .reference import RefOptions

    ex = get_exercise(lid, eid)
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
    if kind in ("find_note", "play_interval"):
        from . import quiz
        return RefOptions(notes=quiz.drawn_notes(lid, ex)), "wait", 1.0, ex.get("min", 80)
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
