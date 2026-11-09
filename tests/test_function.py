"""Harmonic function: jobs of the chords, degrees by ear, cadences, secondary dominants, borrowed chords."""
from guitarr import quiz
from guitarr import theory as th


def _answers(kind, n=30, seed=1, **kw):
    d = quiz.draw("l", dict(id="q", kind="quiz", quiz=kind, count=n, **kw), 80, seed=seed)
    full = quiz._draws[d["token"]]["items"]
    out = [(it, next(c for c in it["choices"] if c["id"] == f["answer"])) for it, f in zip(d["items"], full)]
    quiz.finish(d["token"])
    return out


def test_functions_follow_the_degree():
    for it, right in _answers("function"):
        p = it["prompt"]["params"]
        hz = th.harmonize(p["key"])
        c = next(x for x in hz if p["chord"] in (x["symbol"], x["roman"]))
        assert right["label"]["code"] == "fn_" + quiz.FUNCTION[c["degree"]]


def test_hear_degree_plays_the_tonic_then_the_chord():
    for it, right in _answers("hear_degree", degrees=[1, 4, 5]):
        tonic, other = it["play_chords"]
        assert len(it["play_chords"]) == 2 and right["label"] in ("I", "IV", "V")
        want = {"I": 0, "IV": 5, "V": 7}[right["label"]]
        assert (other[0] - tonic[0]) % 12 == want
    for it, right in _answers("hear_degree", mode="minor", degrees=[1, 4, 6, 7]):
        assert right["label"] in ("i", "iv", "VI", "VII")
        assert (it["play_chords"][1][0] - it["play_chords"][0][0]) % 12 == {"i": 0, "iv": 5, "VI": 8, "VII": 10}[right["label"]]


def test_cadences_by_name_and_by_ear():
    for it, right in _answers("cadence"):
        p = it["prompt"]["params"]
        hz = [c["symbol"] for c in th.harmonize(p["key"])]
        a, b = (hz.index(x.removesuffix("7") if x.removesuffix("7") in hz else x) + 1 for x in (p["a"], p["b"]))
        name = right["label"]["code"][4:]
        assert (b == 5) if name == "half" else quiz.CADENCES[name] == (a, b)
    for it, _ in _answers("cadence", ear=True, n=6):
        assert len(it["play_chords"]) == 3


def test_secondary_dominants_sit_a_fifth_above_their_target():
    for it, right in _answers("secondary"):
        p = it["prompt"]["params"]
        if it["prompt"]["code"] == "secondary_of":
            assert th.pc(right["label"][:-1]) == (th.pc(th.parse_chord(p["chord"])["root"]) + 7) % 12
        else:
            assert (th.pc(th.parse_chord(right["label"])["root"]) + 7) % 12 == th.pc(p["chord"][:-1])


def test_borrowed_chords_come_from_the_parallel_minor():
    for it, right in _answers("borrowed"):
        p = it["prompt"]["params"]
        assert right["label"] == th.harmonize(p["key"], "natural_minor")[quiz.BORROWED[p["roman"]]]["symbol"]
    assert any(r["label"] == "Fm" for it, r in _answers("borrowed", keys=["C"]) if it["prompt"]["params"]["roman"] == "iv")


def test_progressions_name_their_degrees():
    for it, right in _answers("progression"):
        p = it["prompt"]["params"]
        minor = p["key"].endswith("m")
        hz = th.harmonize(p["key"].rstrip("m"), "natural_minor" if minor else "major")
        assert [hz[[c["roman"] for c in hz].index(r)]["symbol"] for r in right["label"].split("–")] == p["chords"].split(" – ")
