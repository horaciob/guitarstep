"""Teacher assignments: a setlist shared as a file, with a note and the teacher's own charts."""
import json

from fastapi.testclient import TestClient

from guitarr import catalog, setlists
from guitarr.gui.server import app

MINE = "title: Teacher riff\nbpm: 70\n\nAm | E7 | Am | E7\n"


def test_export_then_import_on_another_machine(tmp_path, monkeypatch):
    c = TestClient(app)
    mine = catalog.save_chart(MINE)["id"]
    s = c.post("/api/setlists", json=dict(name="Week 3")).json()
    c.put(f"/api/setlists/{s['id']}", json=dict(items=[dict(kind="chart", id="01-em-am"), dict(kind="chart", id=mine),
                                                         dict(kind="song", id="tune.gp5")]))
    r = c.get(f"/api/setlists/{s['id']}/assignment", params=dict(note="Verse at 80 BPM"))
    assert 'filename="week-3.guitarr.json"' in r.headers["content-disposition"]
    data = r.json()
    assert data["note"] == "Verse at 80 BPM" and data["items"][0] == dict(kind="chart", id="01-em-am")
    assert data["items"][1]["text"].startswith("title: Teacher riff") and "text" not in data["items"][2]

    # the student's machine: no charts of their own, no songs, and already a setlist with that name
    catalog.delete_chart(mine)
    imported = c.post("/api/assignments", json=data).json()
    assert imported["setlist"]["name"] == "Week 3 (2)" and imported["setlist"]["note"] == "Verse at 80 BPM"
    assert imported["charts"] == [mine] and imported["missing_songs"] == ["tune.gp5"]
    assert catalog.get_chart(mine)["title"] == "Teacher riff"
    assert [i["id"] for i in imported["setlist"]["items"]] == ["01-em-am", mine, "tune.gp5"]


def test_a_different_chart_with_the_same_id_is_kept():
    c = TestClient(app)
    mine = catalog.save_chart(MINE)["id"]
    data = dict(guitarr_assignment=1, name="X", items=[dict(kind="chart", id=mine, text=MINE.replace("70", "90"))])
    r = c.post("/api/assignments", json=data).json()
    assert r["charts"] == [f"{mine}-teacher"] and catalog.get_chart(mine)["bpm"] == 70
    same = c.post("/api/assignments", json=dict(data, items=[dict(kind="chart", id=mine, text=MINE)])).json()
    assert same["charts"] == []                                                 # identical: nothing new


def test_not_an_assignment():
    c = TestClient(app)
    assert c.post("/api/assignments", json=dict(hello=1)).json()["detail"]["code"] == "not_assignment"
