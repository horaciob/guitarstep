"""Placement: where to start the course when you already play."""
from fastapi.testclient import TestClient

from guitarr import placement, routine
from guitarr.gui.server import app


def test_first_no_is_where_you_start():
    assert placement.start_from([False]) is None
    assert placement.start_from([True, True, False]) == "n3"
    assert placement.start_from([True] * 3) == "n16"                      # stopped answering: the next level
    assert placement.start_from([True] * len(placement.LEVELS)) == placement.LEVELS[-1]


def test_next_lesson_starts_at_the_level_then_wraps():
    first_n5 = placement.next_lesson(set(), "n5")
    assert first_n5["id"] == "barre"
    assert placement.next_lesson(set(), None)["id"] == "strings"


def test_api_moves_the_suggested_lesson_without_passing_anything():
    c = TestClient(app)
    assert c.get("/api/course").json()["next"]["id"] == "strings"
    r = c.post("/api/placement", json=dict(answers=[True, True, True, True, True, False])).json()
    assert r["start_level"] == "n5"
    course = c.get("/api/course").json()
    assert course["next"]["id"] == "barre" and course["start_level"] == "n5"
    assert not any(ls["done"] for lv in course["levels"] for ls in lv["lessons"])
    assert any(s["params"].get("lesson") == "barre" for s in routine.build()["steps"] if s["kind"] == "lesson")
    assert c.get("/api/placement").json()["levels"][0] == dict(id="n1", number=1, title="First sounds")
    assert c.post("/api/placement", json=dict(answers=[])).json()["detail"]["code"] == "bad_answers"
    assert c.post("/api/placement", json=dict(reset=True)).json()["start_level"] is None
    assert c.get("/api/course").json()["next"]["id"] == "strings"
