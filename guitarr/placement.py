"""Where to start the course if you already play: one skill per level, in course order, answered yes or no.
The first "no" is where you start. Nothing is marked as passed: it only moves the suggested next lesson (each
lesson still has its own check to skip it for real)."""
from __future__ import annotations

# the main levels a placement can skip, in course order (later levels are reached by playing)
LEVELS = ["n1", "n2", "n3", "n16", "n4", "n5", "n21", "n23", "n6", "n8", "n9"]


def start_from(answers: list[bool]) -> str | None:
    """The level to start at from the yes/no answers (None: from the very beginning)."""
    for lid, yes in zip(LEVELS, answers):
        if not yes:
            return None if lid == LEVELS[0] else lid
    return LEVELS[len(answers)] if len(answers) < len(LEVELS) else LEVELS[-1]


def next_lesson(done: set[str], start: str | None) -> dict | None:
    """The first lesson not done, from the level you start at (or earlier ones, once those are all done)."""
    from . import catalog

    levels = catalog.course()["levels"]
    k = next((i for i, lv in enumerate(levels) if lv["id"] == start), 0)
    order = levels[k:] + levels[:k]
    return next((x for lv in order for x in lv["lessons"] if x["id"] not in done), None)
