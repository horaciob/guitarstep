"""Reading rhythm: the notation, tap grading, dictation and rhythm played on the guitar."""
import pytest

from guitarr import catalog, quiz
from guitarr import rhythm as rh
from guitarr.reference import load_reference


def test_notation_values_dots_triplets_and_rests():
    assert rh.onsets("q e e rq q") == [0, 1, 1.5, 3]
    assert rh.total_beats("e. s q. e q") == 4
    assert rh.onsets("te te te q te te te q") == pytest.approx([0, 1 / 3, 2 / 3, 1, 2, 7 / 3, 8 / 3, 3], abs=1e-3)
    assert rh.total_beats("rw") == 4 and rh.onsets("rw") == []
    with pytest.raises(rh.RhythmError):
        rh.parse("q x")


def test_every_course_rhythm_fills_one_bar_of_four_four():
    for ls in catalog.lessons():
        for ex in ls["exercises"]:
            for p in ex.get("patterns", []):
                assert rh.total_beats(p) == 4, (ls["id"], p)
        for f in ls.get("figures", []):
            if f.get("type") == "rhythm":
                assert rh.total_beats(f["pattern"]) == 4, (ls["id"], f["pattern"])


def test_taps_are_graded_in_milliseconds():
    beat = 60000 / 60                                    # 60 BPM: one beat = 1000 ms
    perfect = rh.grade_taps("q q q q", 60, [0, 1000, 2000, 3000])
    assert perfect["accuracy"] == 100 and perfect["extra"] == 0 and perfect["mean_abs"] == 0
    late = rh.grade_taps("q q q q", 60, [70, 1070, 2120, 3000])
    assert [h["grade"] for h in late["hits"]] == ["good", "good", "late", "perfect"]
    assert late["hits"][2]["offset"] == 120
    missed = rh.grade_taps("q q q q", 60, [0, 1000])
    assert missed["accuracy"] == 50 and missed["hits"][3]["grade"] == "miss"
    extra = rh.grade_taps("h h", 60, [0, 500, 2 * beat])
    assert extra["extra"] == 1 and extra["accuracy"] == 90
    assert rh.grade_taps("q q q q", 60, "junk")["accuracy"] == 0


def test_tap_exercise_scores_partial_credit_per_bar():
    ex = dict(id="t", kind="tap", bpm=60, patterns=["q q q q", "h h"], count=2)
    d = quiz.draw("lesson", ex, 70, seed=1)
    assert [it["type"] for it in d["items"]] == ["tap", "tap"]
    assert d["items"][0]["rhythm"] == dict(pattern="q q q q", bpm=60, beats=4)
    r = quiz.check(d["token"], 0, [0, 1000, 2000, 3000])
    assert r["correct"] and r["accuracy"] == 100 and len(r["hits"]) == 4
    quiz.check(d["token"], 1, [0])                       # half of the bar
    assert quiz.finish(d["token"])["score"] == 75


def test_dictation_plays_the_bar_without_telling_which_choice_it_is():
    ex = dict(id="d", kind="quiz", quiz="rhythm_dictation", bpm=70, count=6, patterns=["q q q q", "h h", "e e e e q q", "q rq q rq", "q e e h"])
    d = quiz.draw("lesson", ex, 75, seed=3)
    for i, it in enumerate(d["items"]):
        assert it["hear_rhythm"]["pattern"] is None and it["hear_rhythm"]["onsets"]
        assert len(it["choices"]) == 4 and all(c["rhythm"]["pattern"] for c in it["choices"])
        right = next(c for c in it["choices"] if rh.onsets(c["rhythm"]["pattern"]) == it["hear_rhythm"]["onsets"])
        assert quiz.check(d["token"], i, right["id"])["correct"]
    assert quiz.finish(d["token"])["score"] == 100
    for seed in range(20):                               # "h h" and "q rq q rq" sound alike: never both
        import random
        opts = rh.lookalikes(random.Random(seed), "h h", ["h h", "q rq q rq", "q q q q", "w"])
        assert "q rq q rq" not in opts


def test_rhythm_played_on_the_guitar_feeds_the_listener_in_tempo_mode():
    ls = catalog.get_lesson("rhythm-on-guitar")
    ex = ls["exercises"][0]
    d = quiz.draw(ls["id"], ex, 70, seed=2)
    assert len(d["bars"]) == ex["count"] and "phrase" not in d        # read it, don't hear it first
    opts, mode, _, need = catalog.exercise_setup(ls["id"], ex["id"])
    assert mode == "tempo" and need == 70
    ref = load_reference(opts, log=lambda m: None)
    want = sum(len(rh.onsets(b)) for b in d["bars"])
    assert len(ref.notes) == want and all(n.pitch == 40 for n in ref.notes)


def test_reading_rhythm_levels_sit_in_the_course():
    numbers = [lv["number"] for lv in catalog.course()["levels"]]
    assert numbers == list(range(1, len(numbers) + 1))
    ids = [ls["id"] for ls in catalog.lessons()]
    assert ids.index("pulse") < ids.index("blues")
    assert ids.index("sixteenths") > ids.index("degree-map")
