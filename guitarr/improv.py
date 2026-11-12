"""Improvising over a backing: every note you play is heard against the chord of the moment and the scale.

A note is a chord tone, a scale tone or outside. An outside note that steps (1–2 semitones) into a chord or scale
tone right after is an approach note, which is fine. The report also looks at what makes a solo sound like music
rather than a scale: landing on chord tones on the beat, leaving space, using more than a few notes and frets."""
from __future__ import annotations

import numpy as np

from . import groove, theory
from .core import Grid

# Built-in backings: one chorus each, repeated. key/scale = the scale suggested for it.
BACKINGS = {
    "blues_a":  dict(bpm=90, key="A", scale="blues",
                     bars=["A7", "D7", "A7", "A7", "D7", "D7", "A7", "A7", "E7", "D7", "A7", "E7"]),
    "minor_am": dict(bpm=85, key="A", scale="minor_pentatonic", bars=["Am", "Dm", "Am", "Em"]),
    "rock_e":   dict(bpm=110, key="E", scale="minor_pentatonic", bars=["E5", "D5", "A5", "E5"]),
    "pop_c":    dict(bpm=95, key="C", scale="major_pentatonic", bars=["C", "G", "Am", "F"]),
    "dorian_d": dict(bpm=90, key="D", scale="dorian", bars=["Dm7", "G7", "Dm7", "G7"]),
    "jazz_c":   dict(bpm=100, key="C", scale="major", bars=["Dm7", "G7", "Cmaj7", "Cmaj7"]),
}
FOLLOW = "follow"            # scale choice: the scale of each chord (chord-scale), not one for the whole tune

MIN_NOTES = 8                # fewer notes say nothing about a solo
APPROACH_S = 0.5             # an outside note resolved within this time is an approach note


def chart(backing: str, bpm: float, choruses: int) -> dict:
    """A chord chart for the backing (bass, drums and the metronome come with it)."""
    from . import catalog

    b = BACKINGS[backing]
    bars = [dict(chord=c, beats=4, frets=catalog.get_chord(c)["frets"]) for _ in range(choruses) for c in b["bars"]]
    return dict(id=f"improv-{backing}", title=backing, bpm=bpm, beats_per_bar=4, capo=0, bars=bars)


def _power(chord: str) -> bool:
    """"E5", "F#5": a root and its fifth."""
    return len(chord) in (2, 3) and chord.endswith("5") and chord[0] in "ABCDEFG"


def scale_pcs(key: str, scale: str, chord: str | None) -> set[int]:
    """The notes that fit: the chosen scale, or with FOLLOW the scale that goes with the chord."""
    if scale == FOLLOW and chord:
        if _power(chord):                                # no third: the rock sound, minor with a major 6th (dorian)
            return {s["pc"] for s in theory.scale(chord[:-1], "dorian")}
        c = theory.parse_chord(chord)
        return {s["pc"] for s in theory.scale(c["root"], theory.CHORD_SCALE.get(c["quality"], "major"))}
    return {s["pc"] for s in theory.scale(key, scale)}


def chord_pcs(chord: str | None) -> set[int]:
    if not chord:
        return set()
    if _power(chord):                                    # power chord: root and fifth
        r = theory.pc(chord[:-1])
        return {r, (r + 7) % 12}
    return {t["pc"] for t in theory.chord(chord)["tones"]}


def classify(midi: int, chord: str | None, key: str, scale: str) -> str:
    p = midi % 12
    if p in chord_pcs(chord):
        return "chord"
    if p in scale_pcs(key, scale, chord):
        return "scale"
    return "outside"


def report(notes: list[dict], grid: Grid, beats_played: float) -> dict:
    """notes = [{t (reference time), midi, cls, chord}] in order. The summary and the one or two things to work on."""
    n = len(notes)
    if n < MIN_NOTES:
        return dict(n=n, score=None, tips=["play_more"] if n else [])
    cls = [x["cls"] for x in notes]
    # outside notes that resolve by a step right away are approach notes (chromatic passing tones)
    for i, x in enumerate(notes[:-1]):
        nxt = notes[i + 1]
        if x["cls"] == "outside" and nxt["cls"] != "outside" and nxt["t"] - x["t"] <= APPROACH_S \
                and 1 <= abs(nxt["midi"] - x["midi"]) <= 2:
            cls[i] = "approach"
    count = {k: cls.count(k) for k in ("chord", "scale", "approach", "outside")}
    fits = (count["chord"] + count["scale"] + count["approach"]) / n
    on_beat = [c for x, c in zip(notes, cls) if groove.position(grid, x["t"]) == "beat"]
    landing = on_beat.count("chord") / len(on_beat) if on_beat else None
    beats = {int(np.floor(grid.beat_pos(x["t"]))) for x in notes}
    space = max(0.0, 1 - len(beats) / beats_played) if beats_played else 0.0
    span = max(x["midi"] for x in notes) - min(x["midi"] for x in notes)
    distinct = len({x["midi"] for x in notes})
    space_ok = 1.0 if 0.15 <= space <= 0.6 else max(0.0, 1 - abs(space - (0.15 if space < 0.15 else 0.6)) / 0.3)
    score = 100 * (0.6 * fits + 0.25 * (landing if landing is not None else fits) + 0.15 * space_ok)
    tips = []
    if count["outside"] / n > 0.15:
        tips.append("outside")
    if landing is not None and landing < 0.4:
        tips.append("land_chord")
    if space < 0.15:
        tips.append("breathe")
    elif space > 0.7:
        tips.append("play_more")
    if span < 7 or distinct < 5:
        tips.append("range")
    return dict(n=n, score=round(score, 1), fits_pct=round(100 * fits), landing_pct=None if landing is None else round(100 * landing),
                space_pct=round(100 * space), span=int(span), distinct=distinct, counts=count, tips=tips[:2])
