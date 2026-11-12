"""Skills by area for the home radar."""
from guitarr import catalog, progress, skills


def test_empty_progress_is_all_zero():
    s = skills.compute(progress.get())
    assert [x["area"] for x in s] == list(skills.AREAS) and all(x["value"] == 0 for x in s)
    assert all(lid in {lv["id"] for lv in catalog.course()["levels"]} for ids in skills.AREAS.values() for lid in ids)


def test_passed_exercises_and_tools_count():
    p = progress.get()
    lv = next(l for l in catalog.course()["levels"] if l["id"] == "n1")
    for ls in lv["lessons"]:
        for e in ls["exercises"]:
            p["exercises"][f"{ls['id']}/{e['id']}"] = 100
    p["ear"] = {"interval": {"best": 80}, "chord_basic": {"best": 60}}
    p["rhythm"] = {"80": {"within": 90, "std": 20}}
    s = {x["area"]: x for x in skills.compute(p)}
    chords = s["chords"]
    assert chords["passed"] == 18 and chords["value"] == round(100 * 18 / chords["total"])
    assert s["ear"]["value"] == 70 and s["ear"]["tool_kind"] == "ear"
    assert s["rhythm"]["tool"] == 90 and s["rhythm"]["value"] == 45         # (0% of the course + 90) / 2
