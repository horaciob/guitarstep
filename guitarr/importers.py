"""Importers for text tablature (ASCII tab) and MusicXML, turned into a Reference.

ASCII tab ("e|---0---2---|"): one block of string lines per system. String names at the
start of each line give the tuning (e B G D A E, D A D G B E, 7 strings, bass…). Tabs
rarely say the rhythm, so each `|`-delimited bar is spread evenly over 4 beats at the given
tempo (or each column is an eighth note when there are no bar lines). h, p, /, \\, b, r, ~
are read as legato marks and ignored.

MusicXML (.musicxml, .xml, .mxl): the first part with notes; pitches, durations, chords,
ties, backup/forward, time signature and tempo; <string>/<fret> fingerings when present.
Files that declare XML entities are rejected (entity-expansion attacks).
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .core import NOTE_NAMES, Grid, Note, Reference

TAB_EXT = {".tab"}
MUSICXML_EXT = {".musicxml", ".xml", ".mxl"}
DEFAULT_BPM = 80.0
MAX_BYTES = 10 * 1024 * 1024


class ImportError_(ValueError):
    pass


# ---------------------------------------------------------------- ASCII tab
_LINE = re.compile(r"^\s*([A-Ga-g][#b]?)\s*[|:]\s*(.*?)\s*$")
_PC = {n: i for i, n in enumerate(NOTE_NAMES)} | {"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10}
# open strings, low to high, for the usual string counts (when names alone are ambiguous)
_BASE = {4: [28, 33, 38, 43], 5: [23, 28, 33, 38, 43], 6: [40, 45, 50, 55, 59, 64], 7: [35, 40, 45, 50, 55, 59, 64]}


def looks_like_tab(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if _LINE.match(ln) and "-" in ln]
    return len(lines) >= 4


def _tuning_from_names(names: list[str]) -> list[int]:
    """Names from the highest string down → MIDI, low string first (octaves from the usual
    string ranges)."""
    low_first = list(reversed(names))
    base = _BASE.get(len(low_first))
    if base is None:
        raise ImportError_(f"A tab with {len(low_first)} strings isn't supported")
    out = []
    for name, ref in zip(low_first, base):
        pc = _PC.get(name[0].upper() + name[1:])
        if pc is None:
            raise ImportError_(f"Unknown string name: {name}")
        cand = [ref + d for d in range(-6, 7) if (ref + d) % 12 == pc]
        out.append(min(cand, key=lambda p: abs(p - ref)))
    return out


def parse_tab(text: str, bpm: float = DEFAULT_BPM, name: str = "tab") -> Reference:
    blocks, cur = [], []
    for ln in text.splitlines():
        m = _LINE.match(ln)
        if m and "-" in m.group(2):
            cur.append((m.group(1), m.group(2)))
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    blocks = [b for b in blocks if len(b) >= 4]
    if not blocks:
        raise ImportError_("No tablature found (lines like e|---0---|)")
    names = [s for s, _ in blocks[0]]
    tuning_low_first = _tuning_from_names(names)
    nstr = len(names)
    beat = 60.0 / bpm
    notes: list[Note] = []
    t = 0.0
    for block in blocks:
        if len(block) != nstr:
            continue
        rows = [body for _, body in block]
        width = max(len(r) for r in rows)
        rows = [r.ljust(width, "-") for r in rows]
        # bar lines: columns where every string has '|'
        bars = [c for c in range(width) if all(r[c] == "|" for r in rows)]
        edges = [-1] + bars + ([width] if not bars or bars[-1] != width - 1 else [])
        segments = [(a + 1, b) for a, b in zip(edges, edges[1:]) if b - a > 1]
        for a, b in segments:
            cols = b - a
            col_len = (4 * beat / cols) if bars else beat / 2
            c = a
            while c < b:
                hit = False
                for si, r in enumerate(rows):
                    ch = r[c]
                    if ch.isdigit():
                        j = c + 1 if c + 1 < b and r[c + 1].isdigit() else c
                        fret = int(r[c:j + 1])
                        string_no = si + 1                       # first line = highest string = 1
                        open_p = tuning_low_first[nstr - 1 - si]
                        start = t + (c - a) * col_len
                        notes.append(Note(start, start + 2 * col_len, open_p + fret, 0.8, string_no, fret))
                        hit = True
                c += 2 if hit and any(c + 1 < b and r[c].isdigit() and r[c + 1].isdigit() for r in rows) else 1
            t += cols * col_len
    if not notes:
        raise ImportError_("The tablature has no notes")
    notes.sort(key=lambda n: (n.start, n.pitch))
    grid = Grid.from_bpm(bpm, 0.0, 4, t + 10)
    return Reference(notes, grid, name=name, path=name, tuning=list(reversed(tuning_low_first)))


def load_tab(path: Path, bpm: float | None = None) -> Reference:
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ImportError_("The file is too big")
    ref = parse_tab(path.read_text(encoding="utf-8", errors="replace"), bpm or DEFAULT_BPM, path.stem)
    ref.path = str(path)
    return ref


# ---------------------------------------------------------------- MusicXML
_STEP = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)


def _xml_bytes(path: Path) -> bytes:
    if path.stat().st_size > MAX_BYTES:
        raise ImportError_("The file is too big")
    data = path.read_bytes()
    if path.suffix.lower() == ".mxl" or data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = None
            if "META-INF/container.xml" in z.namelist():
                c = _parse(z.read("META-INF/container.xml"))
                rf = next((e for e in c.iter() if e.tag.endswith("rootfile")), None)
                root = rf.get("full-path") if rf is not None else None
            root = root or next((n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF")), None)
            if not root:
                raise ImportError_("No score inside the .mxl file")
            info = z.getinfo(root)
            if info.file_size > MAX_BYTES:
                raise ImportError_("The file is too big")
            data = z.read(root)
    return data


def _parse(data: bytes):
    if b"<!ENTITY" in data:
        raise ImportError_("Files that declare XML entities aren't accepted")
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ImportError_(f"Not a valid MusicXML file: {e}") from None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def load_musicxml(path: Path) -> Reference:
    path = Path(path)
    root = _parse(_xml_bytes(path))
    if _local(root.tag) != "score-partwise":
        raise ImportError_("Only partwise MusicXML scores are supported")
    for el in root.iter():
        el.tag = _local(el.tag)
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or path.stem).strip()
    for part in root.findall("part"):
        ref = _part(part, title, path)
        if ref is not None:
            return ref
    raise ImportError_("The score has no notes")


def _part(part, title: str, path: Path) -> Reference | None:
    divisions, bpm, bpb = 1.0, None, 4
    t = 0.0                  # in quarter notes
    notes: list[Note] = []
    open_ties: dict[int, Note] = {}
    last_start = 0.0
    for measure in part.findall("measure"):
        for el in measure:
            if el.tag == "attributes":
                divisions = float(el.findtext("divisions") or divisions)
                beats = el.findtext("time/beats")
                if beats and beats.isdigit():
                    bpb = int(beats)
            elif el.tag in ("sound", "direction"):
                snd = el if el.tag == "sound" else el.find(".//sound")
                if snd is not None and snd.get("tempo") and bpm is None:
                    bpm = float(snd.get("tempo"))
            elif el.tag == "backup":
                t -= float(el.findtext("duration") or 0) / divisions
            elif el.tag == "forward":
                t += float(el.findtext("duration") or 0) / divisions
            elif el.tag == "note":
                dur = float(el.findtext("duration") or 0) / divisions
                is_chord = el.find("chord") is not None
                start = last_start if is_chord else t
                if not is_chord:
                    t += dur
                    last_start = start
                if el.find("rest") is not None or el.find("pitch") is None or el.find("grace") is not None:
                    continue
                step = el.findtext("pitch/step")
                pitch = 12 * (int(el.findtext("pitch/octave")) + 1) + _STEP[step] + int(float(el.findtext("pitch/alter") or 0))
                ties = {x.get("type") for x in el.findall("tie")}
                if "stop" in ties and pitch in open_ties:          # continues a held note
                    open_ties[pitch].end = start + dur
                    if "start" not in ties:
                        open_ties.pop(pitch)
                    continue
                s = el.findtext("notations/technical/string")
                f = el.findtext("notations/technical/fret")
                n = Note(start, start + dur, pitch, 0.8, int(s) if s else None, int(f) if f else None)
                notes.append(n)
                if "start" in ties:
                    open_ties[pitch] = n
    if not notes:
        return None
    bpm = bpm or DEFAULT_BPM
    q = 60.0 / bpm                    # seconds per quarter note
    for n in notes:
        n.start, n.end = n.start * q, n.end * q
    notes.sort(key=lambda n: (n.start, n.pitch))
    grid = Grid.from_bpm(bpm, 0.0, bpb, notes[-1].end + 10)
    return Reference(notes, grid, name=title, path=str(path), track=part.get("id"))
