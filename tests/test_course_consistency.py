"""The course stays in teaching order: nothing is used before it's taught, and the chord library, the built-in
charts and the Spanish texts all follow the course."""
import json
import re

from guitarr import catalog

ES = json.loads((catalog.DATA_DIR.parent / "gui/static/locales/es.json").read_text(encoding="utf-8"))["content"]


def ordered_lessons():
    """The main course, then the optional courses (which come after it in teaching order)."""
    for lvl in catalog.all_levels():
        for ls in lvl["lessons"]:
            if not ls.get("recap"):
                yield lvl, ls


def test_levels_and_ids():
    levels = catalog.course()["levels"]
    assert [lv["number"] for lv in levels] == list(range(1, len(levels) + 1))
    assert len({lv["id"] for lv in levels}) == len(levels)
    ids = [ls["id"] for _, ls in ordered_lessons()]
    assert len(ids) == len(set(ids)), "duplicate lesson ids"
    for lv in levels:
        assert lv["lessons"], f"level {lv['id']} is empty"


def test_optional_courses_follow_the_main_one():
    main, optional = catalog.course()["levels"], catalog.course()["optional"]
    assert optional, "the heavy-metal course is there"
    assert all(lv.get("track") and lv.get("badge") and lv["lessons"] for lv in optional)
    assert len({lv["badge"] for lv in optional}) == len(optional)
    assert len({lv["id"] for lv in main + optional}) == len(main + optional)
    assert min(lv["number"] for lv in optional) > len(main)          # their charts sit above every main level
    assert not {ls["id"] for ls in catalog.lessons()} & {ls["id"] for lv in optional for ls in lv["lessons"]}


def test_every_chord_is_taught_before_it_is_used():
    taught, problems = set(), []
    for lvl, ls in ordered_lessons():
        taught |= set(ls.get("chords") or [])
        for c in ls.get("chords") or []:
            assert catalog.get_chord(c), f"{ls['id']}: {c} is not in the chord library"
        problems += [f"L{lvl['number']} {ls['id']}: {c}" for c in catalog.lesson_chords(ls) if c not in taught]
    assert not problems, "used before taught:\n" + "\n".join(problems)
    assert {c["id"] for c in catalog.chords()} <= taught, "chords no lesson teaches"


def test_every_built_in_chart_is_used_and_levelled_by_the_course():
    used = catalog.taught_at()["charts"]
    for c in catalog.charts():
        if not c.get("mine") and not c.get("error"):
            assert c["id"] in used, f"chart {c['id']} is in no lesson"
            assert c["level"] == used[c["id"]]


def test_techniques_come_after_their_lesson():
    """Licks only use hammer-ons/pull-offs after the legato lesson, and bends/vibrato after the bends lesson."""
    seen, problems = set(), []
    needs = {"h": "legato", "p": "legato", "b": "bends-vibrato", "~": "bends-vibrato"}
    for lvl, ls in ordered_lessons():
        seen.add(ls["id"])
        for ex in ls["exercises"]:
            if ex["kind"] == "lick":
                for mark in set(re.findall(r"\d([hpb~])", ex["tab"])):
                    if needs[mark] not in seen:
                        problems.append(f"L{lvl['number']} {ls['id']}/{ex['id']}: '{mark}' before {needs[mark]}")
    assert not problems, "\n".join(problems)


def test_chords_are_in_every_group_they_belong_to():
    by = {c["id"]: c for c in catalog.chords()}
    groups = {g["id"] for g in catalog.chord_groups()}
    for c in by.values():
        assert set(c["groups"]) <= groups and c["groups"][0] != "barre"
        assert ("barre" in c["groups"]) == bool(c.get("barre"))
    for cid in ("F", "B", "Bb"):
        assert by[cid]["groups"] == ["major", "barre"]
    for cid in ("Bm", "Fm", "F#m"):
        assert by[cid]["groups"] == ["minor", "barre"]
    assert by["F7"]["groups"] == ["sevenths", "barre"] and by["F"]["lesson"] == "barre"


def test_spanish_texts_follow_the_course():
    for lvl, ls in ordered_lessons():
        assert lvl["id"] in ES["levels"], lvl["id"]
        assert ls["id"] in ES["lessons"], ls["id"]
        for ex in ls["exercises"]:
            assert f"{ls['id']}/{ex['id']}" in ES["exercises"], f"{ls['id']}/{ex['id']}"
    assert {c["id"] for c in catalog.chords()} <= set(ES["chords"])
    assert {g["id"] for g in catalog.chord_groups()} <= set(ES["groups"])


def test_every_lesson_suggests_a_sound_that_exists():
    import re
    from pathlib import Path

    js = (Path(catalog.__file__).parent / "gui/static/lib/rig/presets.js").read_text()
    ids = set()
    for name in ("FACTORY", "ARTISTS"):
        i = js.index(f"export const {name} = {{")
        ids |= set(re.findall(r"^  (\w+): \(\) =>", js[i:js.index("\n};", i)], re.M))
    for ls in catalog.all_lessons():
        assert ls.get("tone") in ids, (ls["id"], ls.get("tone"))
