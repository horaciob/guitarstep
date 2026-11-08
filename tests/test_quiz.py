import pytest

from guitarr import catalog, quiz
from guitarr import theory as th


@pytest.mark.parametrize("kind", sorted(quiz.QUIZ))
def test_every_quiz_type_has_one_right_answer_among_its_choices(kind):
    for seed in range(25):
        d = quiz.draw("l", dict(id="q", kind="quiz", quiz=kind, count=1), 80, seed=seed)
        item = d["items"][0]
        assert "answer" not in item                       # the answer stays on the server
        ids = [c["id"] for c in item["choices"]]
        assert len(ids) == len(set(ids)) >= 2
        labels = [repr(c["label"]) for c in item["choices"]]
        assert len(labels) == len(set(labels)), (kind, labels)
        stored = quiz._draws[d["token"]]["items"][0]["answer"]
        assert stored in ids
        quiz.finish(d["token"])


def test_quiz_scores_once_per_question_and_counts_unanswered_as_wrong():
    d = quiz.draw("l", dict(id="q", kind="quiz", quiz="relative_minor", count=4), 75, seed=1)
    items = quiz._draws[d["token"]]["items"]
    assert quiz.check(d["token"], 0, items[0]["answer"])["correct"]
    wrong = next(c["id"] for c in d["items"][1]["choices"] if c["id"] != items[1]["answer"])
    assert not quiz.check(d["token"], 1, wrong)["correct"]
    assert quiz.check(d["token"], 1, items[1]["answer"])["correct"]                         # a second try is shown…
    r = quiz.finish(d["token"])
    assert r["score"] == 25.0                                                                # …but only the first counts
    with pytest.raises(quiz.QuizError):
        quiz.finish(d["token"])


def test_answers_are_right_music():
    d = quiz.draw("l", dict(id="q", kind="quiz", quiz="scale_degree", keys=["F#"], count=10), 80, seed=3)
    for i, it in enumerate(quiz._draws[d["token"]]["items"]):
        label = next(c["label"] for c in it["choices"] if c["id"] == it["answer"])
        deg = it["prompt"]["params"]["degree"]
        assert label == next(s["note"] for s in th.scale("F#", "major") if s["degree"] == deg)


def test_pick_on_the_fretboard():
    d = quiz.draw("l", dict(id="p", kind="pick", pick="note", notes=["G"], frets=[0, 5], strings=[6, 5, 4], count=1), 80, seed=0)
    it = quiz._draws[d["token"]]["items"][0]
    assert it["expected"] == [[4, 5], [6, 3]]                  # G on the 6th (3) and the 4th (5)
    assert not quiz.check(d["token"], 0, [[6, 3]])["correct"]  # not all of them
    d = quiz.draw("l", dict(id="p", kind="pick", pick="chord", chords=["C"], frets=[0, 3], count=1), 80, seed=0)
    assert quiz.check(d["token"], 0, [[5, 3], [4, 2], [3, 0]])["correct"]       # C E G
    d = quiz.draw("l", dict(id="p", kind="pick", pick="chord", chords=["C"], frets=[0, 3], count=1), 80, seed=0)
    assert not quiz.check(d["token"], 0, [[5, 3], [4, 2]])["correct"]           # the 5th is missing


def test_play_it_draws_feed_the_listener():
    ex = dict(id="f", kind="find_note", strings=[6], frets=[0, 12], notes=["A"], count=3)
    d = quiz.draw("l", ex, 80, seed=2)
    assert len(d["items"]) == 3 and "token" not in d
    assert quiz.drawn_notes("l", ex) == [45, 45, 45]
    iv = dict(id="i", kind="play_interval", intervals=["P5"], strings=[5], frets=[3, 3], count=2)
    quiz.draw("l", iv, 80, seed=0)
    assert quiz.drawn_notes("l", iv) == [48, 55, 48, 55]


def test_run_and_shape_exercises_build_from_theory():
    steps = catalog.exercise_steps(dict(id="s", kind="scale", key="G", scale="major", frets=[2, 5]))
    assert steps[0]["pitch"] % 12 == 7 and all(s["tech"] == "pick" for s in steps)
    line = catalog.exercise_steps(dict(id="g", kind="line", progression=["Dm7", "G7", "Cmaj7"], frets=[3, 8]))
    assert [s["pitch"] % 12 for s in line][:1] == [5]                          # starts on Dm7's 3rd (F)
    shapes = catalog.exercise_shapes(dict(id="v", kind="voiced", progression=["Dm7", "G7", "Cmaj7"], voicing="drop2", sets=["1234"]))
    assert [s["name"] for s in shapes] == ["Dm7", "G7", "Cmaj7"]
    one = catalog.exercise_shapes(dict(id="x", kind="shape", chord="C", voicing="triad", strings="123", inversion=1, near=5))
    assert th.name_chord(th.shape_pitches(one[0]["frets"]))[0] == "C/E"
    hand = catalog.exercise_shapes(dict(id="h", kind="voiced", shapes=[dict(name="Em/B", frets=[-1, 2, 2, 0, 0, 0])]))
    assert hand[0]["frets"] == [-1, 2, 2, 0, 0, 0]
    chart = catalog.chart_from_shapes(shapes, 2)
    assert len(chart["bars"]) == 6
