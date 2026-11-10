import pytest

from guitarr import catalog, quiz
from guitarr import theory as th


@pytest.mark.parametrize("kind", sorted(quiz.QUIZ))
def test_every_quiz_type_has_one_right_answer_among_its_choices(kind):
    for seed in range(25):
        ex = dict(id="q", kind="quiz", quiz=kind, count=1)
        if kind == "theory":                              # asks about the notes of some lessons
            ex["lessons"] = ["blues-shuffle", "blues-thirds", "blues-bends", "blues-answers", "blues-turnaround"]
        d = quiz.draw("l", ex, 80, seed=seed)
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


def test_quiz_over_the_api_records_progress():
    from fastapi.testclient import TestClient
    from guitarr.gui.server import app

    c = TestClient(app)
    d = c.post("/api/exercise/draw", json=dict(lesson="intervals", exercise="interval-frets-quiz")).json()
    assert len(d["items"]) == 6 and "answer" not in d["items"][0]
    for i in range(6):
        right = quiz._draws[d["token"]]["items"][i]["answer"]
        assert c.post("/api/exercise/check", json=dict(token=d["token"], index=i, answer=right)).json()["correct"]
    r = c.post("/api/exercise/finish", json=dict(token=d["token"])).json()
    assert r["summary"]["score"] == 100 and r["award"]["passed"] and r["award"]["xp"] > 0
    assert c.get("/api/progress").json()["exercises"]["intervals/interval-frets-quiz"] == 100
    assert c.post("/api/exercise/finish", json=dict(token=d["token"])).status_code == 400   # once only
    assert c.post("/api/exercise/draw", json=dict(lesson="intervals", exercise="nope")).status_code == 404


def test_theory_endpoints():
    from fastapi.testclient import TestClient
    from guitarr.gui.server import app

    c = TestClient(app)
    assert [n["note"] for n in c.get("/api/theory/scale?key=Gb&name=major").json()["notes"]][3] == "Cb"
    assert c.get("/api/theory/chord?symbol=H7").status_code == 400
    vs = c.get("/api/theory/voicings?chord=Cmaj7&kind=drop2").json()["voicings"]
    assert vs and all(len(v["frets"]) == 6 for v in vs)
    assert c.post("/api/theory/name", json=dict(frets=[-1, 3, 2, 0, 1, 0])).json()["names"][0] == "C"
    assert c.post("/api/theory/name", json=dict(frets=[1, 2])).status_code == 400
    r = c.post("/api/theory/voice-lead", json=dict(progression="Dm7 G7 Cmaj7", kind="shell")).json()
    assert [s["name"] for s in r["shapes"]] == ["Dm7", "G7", "Cmaj7"]
    assert c.post("/api/theory/voice-lead", json=dict(progression="Dm7")).json()["detail"]["code"] == "bad_progression"
    course = c.get("/api/course").json()
    fig = next(ls for lv in course["levels"] for ls in lv["lessons"] if ls["id"] == "degree-map")["figures"][0]
    assert fig["type"] == "fretboard" and any(m["kind"] == "root" and m["text"] == "1" for m in fig["marks"])


def test_jazz_charts_swing_and_voicing_headers():
    from guitarr.reference import load_reference, RefOptions
    c = catalog.parse_chart("title: t\nbpm: 60\nswing: light\nvoicing: drop2\nstrum: D.D.D..^\nDm7 | G7 | Cmaj7 | C#m7b5\n")
    assert c["swing"] == 0.6 and not c["missing"] and all(b["frets"] for b in c["bars"])
    with pytest.raises(catalog.CatalogError):
        catalog.parse_chart("swing: wobbly\nC | G\n")
    half = catalog.parse_chart("bpm: 60\nswing: hard\nC G | C\n")
    assert half["swing"] == 0.67
    off = dict(title="t", bpm=60, beats_per_bar=4, swing=0.6,
               bars=[dict(chord="C", beats=0.5, frets=[-1, 3, 2, 0, 1, 0]), dict(chord="G", beats=3.5, frets=[3, 2, 0, 0, 0, 3])])
    ref = load_reference(RefOptions(chart=off), log=lambda m: None)
    assert min(n.start for n in ref.notes if n.label == "G") == pytest.approx(0.6)   # the offbeat chord swings late


def test_tone_rows_use_all_twelve_notes():
    ex = dict(id="r", kind="tone_row", frets=[0, 5], count=12)
    quiz.draw("l", ex, 75, seed=7)
    assert sorted(p % 12 for p in quiz.drawn_notes("l", ex)) == list(range(12))


def test_theory_questions_blank_a_glossary_word_of_a_real_note():
    import json
    from pathlib import Path

    recaps = [ls for ls in catalog.all_lessons() if ls.get("recap")]
    checks = [e for ls in recaps for e in ls["exercises"] if e["id"] == "theory-check"]
    assert len(checks) >= 10                               # most levels review their notes
    es = json.loads((Path(catalog.__file__).parent / "gui/static/locales/es.json").read_text())["content"]
    notes = {f"{ls['id']}/{e['id']}": e["theory"] for ls in catalog.all_lessons() if not ls.get("recap") for e in ls["exercises"]}
    for ex in checks:
        for seed in range(10):
            q = quiz.q_theory(__import__("random").Random(seed), ex)
            p = q["prompt"]["params"]
            assert notes[p["key"]] == p["en"] and p["key"] in es["ex_theory"]
            assert p["key"].split("/")[0] in ex["lessons"]        # from this level
            forms = [p["term_en"], *p["aliases_en"]]
            assert any(f.lower() in p["en"].lower() for f in forms)
            # the right word is one of the four, and no other option also fits the sentence
            assert len(q["choices"]) == 4 and q["choices"][int(q["answer"])]["label"]["params"]["id"] == p["term"]
            fams = [quiz.TERM_FAMILY.get(c["label"]["params"]["id"], c["label"]["params"]["id"]) for c in q["choices"]]
            assert fams.count(quiz.TERM_FAMILY.get(p["term"], p["term"])) == 1
    assert quiz.same_word("extension", ["extensions", "tension"]) == ["extension", "extensions"]
