"""The daily warm-up: drills built from theory, a key and position that rotate, and a tempo goal that rises."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from guitarr import progress, warmup
from guitarr import theory as th
from guitarr.reference import RefOptions, load_reference


@pytest.mark.parametrize("drill", warmup.ORDER)
def test_every_drill_in_every_key_and_position_fits_the_neck(drill):
    for p in range(12):
        key = th.plain_name(p)
        for pos in range(warmup.DRILLS[drill]["positions"]):
            st = warmup.steps(drill, key, pos)
            assert len(st) >= 8
            assert all(0 <= x["fret"] <= 20 and x["pitch"] == th.fret_pitch(x["string"], x["fret"]) for x in st)
            assert max(x["fret"] for x in st) - min(x["fret"] for x in st) <= 8
            ivs = dict(pentatonic=warmup.MINOR_PENT, legato=warmup.MINOR_PENT, major=warmup.MAJOR, octaves=list(range(6)),
                       caged=[0, 4, 7], sweep=[0, 4, 7], arpeggios=[0, 3, 4, 7]).get(drill)
            if ivs:                                                          # every note belongs to the key
                assert {(x["pitch"] - p) % 12 for x in st} <= set(ivs), (drill, key, pos)


def test_shapes_are_what_they_say():
    box1 = warmup.steps("pentatonic", "A", 0)
    assert [(x["string"], x["fret"]) for x in box1[:6]] == [(6, 5), (6, 8), (5, 5), (5, 7), (4, 5), (4, 7)]
    assert box1 == box1[:12] + box1[:11][::-1]                                 # up and back down
    assert {x["pitch"] % 12 for x in warmup.steps("major", "G", 3)} == {7, 9, 11, 0, 2, 4, 6}
    assert all(len([x for x in warmup.steps("major", "C", k)[:18] if x["string"] == s]) == 3 for k in range(7) for s in (6, 5, 4))
    arp = warmup.steps("arpeggios", "A", 0)
    top = max(x["pitch"] for x in arp)
    assert [x["pitch"] for x in arp].count(top) == 1                           # no repeated note at the turn
    assert {x["pitch"] % 12 for x in arp} == {9, 1, 4, 0}                       # A major up (C#), A minor down (C)
    octs = warmup.steps("octaves", "E", 0)
    assert all(b["pitch"] - a["pitch"] == 12 for a, b in zip(octs[::2], octs[1::2]))
    leg = warmup.steps("legato", "A", 0)
    assert leg[0]["tech"] == "pick" and leg[1]["tech"] == "hammer" and {x["tech"] for x in leg} == {"pick", "hammer", "pull"}


def test_the_day_picks_the_drill_then_key_and_position_move():
    d0 = date(2026, 1, 5)
    days = [warmup.today_plan(d0 + timedelta(days=i)) for i in range(len(warmup.ORDER) * 3)]
    assert {d["drill"] for d in days[:len(warmup.ORDER)]} == set(warmup.ORDER)
    assert days[0]["key"] != days[len(warmup.ORDER)]["key"]                    # a new key after each round


def test_a_clean_take_at_the_goal_raises_it():
    assert warmup.next_goal(60, 60, 92) == 64
    assert warmup.next_goal(60, 70, 95) == 74                                  # faster than the goal: from there
    assert warmup.next_goal(60, 60, 85) == 60 and warmup.next_goal(60, 55, 100) == 60 and warmup.next_goal(60, 60, None) == 60
    out = progress.on_session(dict(type="warmup", drill="spider", bpm=60), dict(summary=dict(score=95, judged=40)))
    assert out["raised"] and out["goal"] == 64 and out["xp"] == 5
    assert progress.get()["warmup"]["spider"]["bpm"] == 64
    out = progress.on_session(dict(type="warmup", drill="spider", bpm=64), dict(summary=dict(score=70, judged=40)))
    assert not out["raised"] and out["goal"] == 64 and progress.get()["warmup"]["spider"]["best"] == 95


def test_warmup_api_and_listener_reference():
    from guitarr.gui.server import app, ref_options
    c = TestClient(app)
    w = c.get("/api/warmup").json()
    assert w["drill"] == w["today"]["drill"] and w["steps"] and w["goal"] == warmup.DRILLS[w["drill"]]["start_bpm"]
    w = c.get("/api/warmup", params=dict(drill="caged", key="G", position=2)).json()
    assert w["label"] == dict(code="shape", params=dict(shape="G")) and len(w["drills"]) == len(warmup.ORDER)
    assert c.get("/api/warmup", params=dict(drill="nope")).status_code == 400
    assert c.get("/api/warmup", params=dict(surprise=1)).json()["drill"] in warmup.ORDER
    opts, ctx = ref_options(dict(warmup=dict(drill="spider", key="A", position=0, bpm=72)))
    assert ctx == dict(type="warmup", mode="tempo", drill="spider", bpm=72.0)
    ref = load_reference(opts, log=lambda m: None)
    assert len(ref.notes) == 48
