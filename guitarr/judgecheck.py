"""Measures the chord judge on your own recordings, to tune it for a real guitar (the thresholds were set with
synthesized strums).

Lay the recordings out by the chord you were asked for, each file named after what you actually played:

    recordings/
      G/ok-1.wav        G, played right
      G/ok-2.wav
      G/Em-1.wav        asked for G, played Em on purpose
      Am/ok-1.wav
      Am/A-1.wav        a major/minor swap

One strum per file (the first one heard is judged). The report counts false mistakes (right chords flagged as
wrong: the worst kind), wrong chords caught, and major/minor swaps caught."""
from __future__ import annotations

from pathlib import Path

from . import catalog
from .reference import AUDIO_EXT, RefOptions, load_reference

OK = "ok"


def _swap(asked: str, played: str) -> bool:
    """G vs Gm, Am vs A: same root, major and minor swapped."""
    strip = lambda c: c[:-1] if c.endswith("m") and not c.endswith("dim") else c
    return asked != played and strip(asked) == strip(played)


def judge_file(asked: str, wav: Path) -> str:
    """What the listener made of one strum: ok | wrong | nothing (no strum heard)."""
    from .session import LiveOptions, LiveSession

    ref = load_reference(RefOptions(chart=catalog.chart_from_chord(asked)), log=lambda m: None)
    rep = LiveSession(ref, LiveOptions(mode="wait", simulate=wav, fast=True, legato=False, count_extras=False)).run()
    s = rep["summary"]
    if not s.get("judged"):
        return "nothing"
    return "ok" if s.get("first_try") else "wrong"


def run(folder: Path, log=print) -> dict:
    folder = Path(folder)
    rows = []
    for d in sorted(p for p in folder.iterdir() if p.is_dir()):
        asked = d.name
        if catalog.get_chord(asked) is None:
            log(f"  skipped {d.name}/: not a chord in the dictionary")
            continue
        for f in sorted(p for p in d.iterdir() if p.suffix.lower() in AUDIO_EXT):
            played = f.stem.split("-")[0]
            if played != OK and catalog.get_chord(played) is None:
                log(f"  skipped {d.name}/{f.name}: name it ok-… or after the chord you played (Em-1.wav)")
                continue
            heard = judge_file(asked, f)
            rows.append(dict(file=f"{d.name}/{f.name}", asked=asked, played=asked if played == OK else played, heard=heard))
    right = [r for r in rows if r["played"] == r["asked"]]
    wrong = [r for r in rows if r["played"] != r["asked"]]
    swaps = [r for r in wrong if _swap(r["asked"], r["played"])]
    count = lambda xs, h: sum(r["heard"] == h for r in xs)
    return dict(
        files=len(rows), rows=rows,
        right=len(right), false_mistakes=count(right, "wrong"), missed_strums=count(rows, "nothing"),
        wrong=len(wrong), caught=count(wrong, "wrong"),
        swaps=len(swaps), swaps_caught=count(swaps, "wrong"),
    )


def print_report(r: dict) -> None:
    for row in r["rows"]:
        good = (row["heard"] == "ok") == (row["played"] == row["asked"])
        print(f"  {'✓' if good else '✗'} {row['file']:30s} asked {row['asked']:6s} played {row['played']:6s} → heard {row['heard']}")
    print()
    print(f"Files: {r['files']}  (no strum heard in {r['missed_strums']})")
    if r["right"]:
        print(f"False mistakes : {r['false_mistakes']} of {r['right']} chords played right")
    if r["wrong"]:
        print(f"Wrong caught   : {r['caught']} of {r['wrong']} wrong chords")
    if r["swaps"]:
        print(f"Major/minor    : {r['swaps_caught']} of {r['swaps']} swaps caught")
