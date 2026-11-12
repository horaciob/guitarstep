"""Your skills by area, for the radar on the home page: how much of each area you've shown you can play.

Each area is the share of its course exercises you passed (a lesson tested out counts as passed), blended with
what the tools measured when there is something: the ear trainer for the ear, the rhythm test for timing,
improvising for the solo area. Every value is 0–100 and comes with the numbers it was made from."""
from __future__ import annotations

AREAS = {
    "chords":    ["n1", "n2", "n4", "n5"],
    "rhythm":    ["n3", "n16", "n17"],
    "technique": ["n21", "n22", "n23"],
    "neck":      ["n8", "n18", "n19"],
    "scales":    ["n9", "n10"],
    "harmony":   ["n11", "n12", "n20", "n13"],
    "blues":     ["n6", "n7"],
    "jazz":      ["n14", "n15"],
    "ear":       [],
}


def compute(p: dict) -> list[dict]:
    from . import catalog

    levels = {lv["id"]: lv for lv in catalog.course()["levels"]}
    out = []
    for area, ids in AREAS.items():
        total = passed = 0
        for lid in ids:
            for ls in levels[lid]["lessons"]:
                for e in ls["exercises"]:
                    total += 1
                    passed += p["exercises"].get(f"{ls['id']}/{e['id']}", -1) >= e.get("min", 80)
        course = 100 * passed / total if total else None
        tool, tool_kind = None, None
        if area == "ear":
            bests = [v.get("best") for v in (p.get("ear") or {}).values() if v.get("best") is not None]
            tool, tool_kind = (sum(bests) / len(bests), "ear") if bests else (None, None)
        elif area == "rhythm" and p.get("rhythm"):
            tool, tool_kind = max(r.get("within", 0) for r in p["rhythm"].values()), "rhythm"
        elif area == "scales" and p.get("improv"):
            tool, tool_kind = max(r.get("best", 0) for r in p["improv"].values()), "improv"
        parts = [x for x in (course, tool) if x is not None]
        value = round(sum(parts) / len(parts)) if parts else 0
        out.append(dict(area=area, value=value, passed=passed, total=total,
                        tool=None if tool is None else round(tool), tool_kind=tool_kind))
    return out
