"""Turns a chord sheet as it's usually shared into a guitarr chart.

Two common shapes are read:
- chords over lyrics: a line of chords, then the lyric line they sit on (the column of each chord says where);
- ChordPro: chords inline in brackets, "[G]Here I [D]am", with {title: ...} and {artist: ...} directives.
Section names ("[Chorus]", "Verse 2:") start sections. Each chord becomes one bar, with its piece of lyric."""
from __future__ import annotations

import re

CHORD = re.compile(r"^[A-G](?:#|b)?(?:maj|min|m|M|dim|aug|sus|add|°|ø|\+)?\d*(?:(?:sus|add|maj|b|#)\d+)*(?:\([^)]*\))?(?:/[A-G](?:#|b)?)?$")
SECTION = re.compile(r"^\s*\[?\s*(intro|verse|pre-?chorus|chorus|bridge|solo|outro|interlude|instrumental|coda|"
                     r"intro|estrofa|verso|estribillo|coro|puente|final)\b[^\]]*\]?\s*:?\s*$", re.I)
NOISE = {"|", "/", "-", "x2", "x3", "x4", "(x2)", "(x3)", "(x4)", "%", "N.C.", "NC"}


def is_chord(tok: str) -> bool:
    return bool(CHORD.match(tok))


def chord_line(line: str) -> bool:
    toks = [t for t in line.split() if t not in NOISE]
    return bool(toks) and all(is_chord(t) for t in toks)


def _clean(s: str) -> str:
    return " ".join(s.replace("|", "/").split())


def _split_lyric(lyric: str, cols: list[int]) -> list[str]:
    """The piece of the lyric under each chord, cutting at word starts (a chord mid-word takes the whole word)."""
    cuts = []
    for c in cols:
        c = min(c, len(lyric))
        while 0 < c < len(lyric) and lyric[c - 1] != " ":
            c -= 1
        cuts.append(c)
    cuts[0] = 0                                     # words before the first chord go with it
    return [_clean(lyric[a:b]) for a, b in zip(cuts, cuts[1:] + [len(lyric)])]


def _row(chords: list[str], words: list[str] | None) -> list[str]:
    out = [" | ".join(chords)]
    if words and any(words):
        out.append("> " + " | ".join(words))
    return out


def convert(text: str) -> dict:
    """{text: the chart text, title, artist, bars, sections} from a chord sheet. Raises ValueError if no chords."""
    lines = text.replace("\t", "    ").splitlines()
    title = artist = None
    body: list[str] = []
    bars = sections = 0
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip()
        i += 1
        m = re.match(r"^\s*\{\s*(title|t|artist|subtitle|st)\s*:\s*(.*?)\s*\}\s*$", raw, re.I)
        if m:
            if m.group(1).lower() in ("title", "t"):
                title = m.group(2)
            else:
                artist = m.group(2)
            continue
        if not raw.strip() or re.match(r"^\s*\{.*\}\s*$", raw):
            continue
        if SECTION.match(raw) and not chord_line(raw.strip("[]: ")):
            body += ["", f"[{raw.strip().strip('[]:').strip().title()}]"]
            sections += 1
            continue
        if "[" in raw and re.search(r"\[([^\]]+)\]", raw):            # ChordPro inline
            parts = re.split(r"\[([^\]]+)\]", raw)
            if all(is_chord(c.strip()) for c in parts[1::2]):
                chords, words = [], []
                lead = parts[0]
                for k in range(1, len(parts), 2):
                    chords.append(parts[k].strip())
                    words.append(_clean((lead if k == 1 else "") + parts[k + 1]))
                body += _row(chords, words)
                bars += len(chords)
                continue
        if chord_line(raw):
            toks = [(mm.start(), mm.group()) for mm in re.finditer(r"\S+", raw) if mm.group() not in NOISE]
            chords, cols = [t for _, t in toks], [c for c, _ in toks]
            nxt = lines[i].rstrip() if i < len(lines) else ""
            if nxt.strip() and not chord_line(nxt) and not SECTION.match(nxt):
                i += 1
                body += _row(chords, _split_lyric(nxt, cols))
            else:
                body += _row(chords, None)
            bars += len(chords)
            continue
        if title is None and not bars and not body:                    # a first plain line: the title
            title = raw.strip()
    if not bars:
        raise ValueError("No chords found: write the chords on their own line above the lyrics, or inline like [G].")
    head = [f"title: {title or 'My song'}"] + ([f"artist: {artist}"] if artist else []) + ["bpm: 80", ""]
    while body and not body[0]:
        body.pop(0)
    return dict(text="\n".join(head + body) + "\n", title=title, artist=artist, bars=bars, sections=sections)
