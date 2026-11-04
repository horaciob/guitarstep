"""Learning content: chord dictionary, chord charts and the course.

- guitarr/data/chords.json   : fingerings (6th→1st string, -1 = not played)
- guitarr/data/charts/*.txt  : built-in exercises, in the text format below
- ~/.guitarr/charts/*.txt    : your own charts
- guitarr/data/course.json   : levels → lessons → exercises you pass by playing

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


# ---------------------------------------------------------------- course
@lru_cache(maxsize=None)
def course() -> dict:
    return json.loads((DATA_DIR / "course.json").read_text(encoding="utf-8"))


def lessons() -> list[dict]:
    return [ls for lvl in course()["levels"] for ls in lvl["lessons"]]


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
