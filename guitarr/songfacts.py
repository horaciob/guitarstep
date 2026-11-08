"""What a song file says about itself: title, artist, tempo, key, time signature, tuning and sections.

Guitar Pro files carry most of it (the sections come from their markers). Other formats give what they
can (at least the name). Used to pre-fill a song's sections and to warn when a setlist changes tuning.
"""
from __future__ import annotations

from pathlib import Path

from .core import TUNINGS

GP_EXT = {".gp3", ".gp4", ".gp5", ".gtp"}
KEYS = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"]   # by sharps: -7 … +7


def tuning_id(pitches_low_to_high: list[int]) -> str | None:
    """The name of a known tuning (6 strings, low to high), or None when it's something else."""
    by_high = list(reversed(pitches_low_to_high))
    for name, t in TUNINGS.items():
        if list(t) == by_high:
            return name
    return None


def facts(path: Path, track: str | None = None) -> dict:
    out = dict(title=path.stem, artist=None, bpm=None, key=None, time=None, tuning=None, tuning_notes=None,
               capo=0, sections=[])
    if path.suffix.lower() in GP_EXT:
        try:
            out.update(_gp(path, track))
        except Exception as e:                     # a file we can't read still has a name
            out["error"] = str(e)
    return out


def _gp(path: Path, track: str | None) -> dict:
    import guitarpro

    song = guitarpro.parse(str(path))
    tracks = [t for t in song.tracks if not t.isPercussionTrack]
    tr = next((t for t in tracks if t.name == track), tracks[0] if tracks else None)
    out: dict = dict(title=song.title.strip() or path.stem, artist=song.artist.strip() or None, bpm=float(song.tempo) or None)
    try:
        sharps = int(song.key.value[0]) if isinstance(song.key.value, tuple) else int(song.key.value)
        minor = isinstance(song.key.value, tuple) and song.key.value[1] == 1
        name = KEYS[sharps + 7]
        out["key"] = name + ("m" if minor else "")
    except (AttributeError, ValueError, IndexError, TypeError):
        out["key"] = None
    hs = song.measureHeaders
    if hs:
        ts = hs[0].timeSignature
        out["time"] = f"{ts.numerator}/{ts.denominator.value}"
    if tr is not None and len(tr.strings) == 6:
        low_to_high = sorted(s.value for s in tr.strings)
        out["tuning"] = tuning_id(low_to_high) or "custom"
        names = "C C# D D# E F F# G G# A A# B".split()
        out["tuning_notes"] = " ".join(names[p % 12] for p in low_to_high)
        out["capo"] = int(getattr(tr, "offset", 0) or 0)
    # sections from the markers: each runs until the next marker (or the end)
    marks = [(h.number, h.marker.title.strip()) for h in hs if h.marker is not None and h.marker.title.strip()]
    secs = []
    seen: dict[str, int] = {}
    for i, (bar, name) in enumerate(marks):
        end = marks[i + 1][0] - 1 if i + 1 < len(marks) else len(hs)
        seen[name] = seen.get(name, 0) + 1
        secs.append({"name": name, "from": bar, "to": max(bar, end),
                     "key": name if seen[name] == 1 else f"{name} ({seen[name]})"})
    out["sections"] = secs
    return out

