"""CAGED: the five shapes of a chord, finding them on the neck and playing them."""
import pytest

from guitarr import catalog, quiz
from guitarr import theory as th


def frets(c):
    return [(s, f) for s, f, _ in c["path"]]


def test_the_five_shapes_of_c():
    assert frets(th.caged("C", "maj", "A")) == [(6, 3), (5, 3), (4, 5), (3, 5), (2, 5), (1, 3)]     # x-3-5-5-5-3
    e = th.caged("C", "maj", "E")
    assert (e["lo"], e["root_fret"]) == (8, 8) and frets(e)[0] == (6, 8)
    assert th.caged("C", "maj", "C")["lo"] == 0                                             # the open C chord
    assert [c["shape"] for c in th.caged_along("C")] == list("CAGED")                       # the order up the neck
    for c in th.caged_along("F#"):
        assert c["hi"] - c["lo"] == 3 and {p % 12 for _, _, p in c["path"]} == {6, 10, 1}
    assert {p % 12 for _, _, p in th.caged("A", "min", "E")["path"]} == {9, 0, 4}
    with pytest.raises(th.TheoryError):
        th.caged("C", "maj", "X")


def test_find_the_chord_in_a_shape():
    ex = dict(id="p", kind="pick", pick="caged", caged="CAGED", count=10)
    d = quiz.draw("l", ex, 80, seed=7)
    for i, it in enumerate(d["items"]):
        full = quiz._draws[d["token"]]["items"][i]
        assert it["mode"] == "all" and it["frets"][1] - it["frets"][0] == 3
        assert quiz.check(d["token"], i, full["expected"])["correct"]
    assert quiz.finish(d["token"])["score"] == 100


def test_playing_the_shapes_runs_up_the_neck():
    ls = catalog.get_lesson("caged-connect")
    ex = next(e for e in ls["exercises"] if e["kind"] == "caged")
    steps = catalog.exercise_steps(ex)
    los = [c["lo"] for c in th.caged_along("G")]
    assert steps[0]["fret"] <= los[0] + 3 and steps[-1]["fret"] >= los[-1]
    v = catalog.variation(ex)
    assert v["chord"] == "C" and catalog.exercise_steps(v)


def test_caged_quiz_answers_are_right():
    d = quiz.draw("l", dict(id="q", kind="quiz", quiz="caged", count=30), 80, seed=2)
    for it in d["items"]:
        code, p = it["prompt"]["code"], it["prompt"]["params"]
        right = next(c for c in it["choices"] if c["id"] == quiz._draws[d["token"]]["items"][d["items"].index(it)]["answer"])
        if code == "caged_next":
            assert right["label"]["params"]["shape"] == "CAGED"[("CAGED".index(p["shape"]) + 1) % 5]
        elif code == "caged_chord":
            assert th.pc(right["label"]) == th.fret_pitch(p["string"], p["fret"]) % 12
        else:
            assert right["label"]["params"]["n"] == th.CAGED[p["shape"]]["string"]
    quiz.finish(d["token"])
