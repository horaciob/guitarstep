"""Reading standard notation: where guitar notes are written, and the three ways to answer."""
from guitarr import catalog, quiz
from guitarr import theory as th
from guitarr.reference import load_reference


def test_guitar_is_written_an_octave_up_in_the_treble_clef():
    assert th.staff_note(59) == dict(step=0, acc=0, name="B")          # open B string: the middle line
    assert th.staff_note(55)["step"] == -2                               # open G: the second line
    assert th.staff_note(64)["step"] == 3                                # open high E: the top space
    assert th.staff_note(40)["step"] == -11                              # open low E: three ledger lines down
    assert th.staff_note(42) == dict(step=-10, acc=1, name="F#")
    assert th.staff_note(42, flats=True) == dict(step=-9, acc=-1, name="Gb")


def test_name_the_written_note():
    ex = dict(id="r", kind="quiz", quiz="read_note", frets=[0, 5], strings=[6, 5], notes="naturals", count=12)
    d = quiz.draw("l", ex, 80, seed=4)
    for i, it in enumerate(d["items"]):
        (note,) = it["staff"]
        right = next(c for c in it["choices"]
                     if any(th.staff_note(th.fret_pitch(s, f)) == {**note, "name": c["label"]} for s in (6, 5) for f in range(6)))
        assert quiz.check(d["token"], i, right["id"])["correct"]
    assert quiz.finish(d["token"])["score"] == 100


def test_accidentals_are_spelled_both_ways_and_choices_match():
    ex = dict(id="r", kind="quiz", quiz="read_note", frets=[0, 5], notes="all", count=40)
    d = quiz.draw("l", ex, 80, seed=9)
    accs = {it["staff"][0]["acc"] for it in d["items"]}
    assert accs == {-1, 0, 1}
    for it in d["items"]:
        labels = {c["label"] for c in it["choices"]}
        assert not ({"C#", "F#"} & labels and {"Db", "Gb"} & labels)         # one spelling per question
    quiz.finish(d["token"])


def test_click_the_written_note_at_its_exact_height():
    ex = dict(id="p", kind="pick", pick="staff", frets=[0, 5], strings=[6, 5, 4, 3, 2, 1], count=1)
    d = quiz.draw("l", ex, 80, seed=1)
    it = d["items"][0]
    assert it["mode"] == "pitch" and it["staff"] and "expected" not in it
    pitch = quiz._draws[d["token"]]["items"][0]["want"][0]
    places = [(s, f) for s in range(1, 7) for f in range(6) if th.fret_pitch(s, f) == pitch]
    octave = [(s, f) for s in range(1, 7) for f in range(6) if th.fret_pitch(s, f) % 12 == pitch % 12 and th.fret_pitch(s, f) != pitch]
    if octave:
        assert not quiz._check_pick(quiz._draws[d["token"]]["items"][0], [list(octave[0])])
    r = quiz.check(d["token"], 0, [list(places[-1])])
    assert r["correct"] and sorted(map(tuple, r["answer"])) == sorted(places)


def test_read_and_play_feeds_the_listener_exact_pitches():
    ls = catalog.get_lesson("read-and-play")
    ex = ls["exercises"][0]
    d = quiz.draw(ls["id"], ex, 80, seed=5)
    assert all(it["staff"] for it in d["items"])
    opts, mode, _, _ = catalog.exercise_setup(ls["id"], ex["id"])
    ref = load_reference(opts, log=lambda m: None)
    assert mode == "wait" and len(ref.notes) == ex["count"]
    assert all(th.plain_name(n.pitch) in quiz.NATURALS and 40 <= n.pitch <= 69 for n in ref.notes)


def test_staff_figures_come_from_the_theory_engine():
    from fastapi.testclient import TestClient

    from guitarr.gui.server import app
    course = TestClient(app).get("/api/course").json()
    ls = next(x for lv in course["levels"] for x in lv["lessons"] if x["id"] == "naturals-low")
    assert [n["name"] for n in ls["figures"][0]["notes"]] == ["E", "F", "G", "A"]


def test_name_the_marked_note_on_the_neck():
    d = quiz.draw("l", dict(id="n", kind="quiz", quiz="name_note", frets=[12, 17], strings=[6, 5], count=12), 80, seed=3)
    for i, it in enumerate(d["items"]):
        (m,) = it["neck"]["marks"]
        assert 12 <= m["fret"] <= 17 and it["neck"]["lo"] <= m["fret"] <= it["neck"]["hi"]
        right = next(c for c in it["choices"] if c["label"] == th.plain_name(th.fret_pitch(m["string"], m["fret"])))
        assert quiz.check(d["token"], i, right["id"])["correct"]
    quiz.finish(d["token"])
