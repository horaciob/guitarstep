"""Songs and the stage (roadmap F): song facts, sections, videos, setlists, readiness."""
import guitarpro
from fastapi.testclient import TestClient
from guitarpro import models as m

from guitarr import config, songfacts
from guitarr.gui.server import app


def make_gp(path, tuning=(38, 45, 50, 55, 59, 64), markers=((1, "Intro"), (3, "Verse"), (5, "Verse"))):
    song = m.Song(tempo=96)
    song.title, song.artist = "Test tune", "Nobody"
    for _ in range(5):
        song.newMeasure()
    tr = song.tracks[0]
    tr.name = "Guitar"
    tr.strings = [m.GuitarString(i + 1, v) for i, v in enumerate(sorted(tuning, reverse=True))]
    for bar, name in markers:
        song.measureHeaders[bar - 1].marker = m.Marker(title=name)
    guitarpro.write(song, str(path))
    return path


def test_guitar_pro_facts_and_sections(tmp_path):
    f = songfacts.facts(make_gp(tmp_path / "t.gp5"))
    assert f["title"] == "Test tune" and f["artist"] == "Nobody" and f["bpm"] == 96
    assert f["tuning"] == "drop_d" and f["tuning_notes"].startswith("D A D")
    assert [(s["key"], s["from"], s["to"]) for s in f["sections"]] == [("Intro", 1, 2), ("Verse", 3, 4), ("Verse (2)", 5, 6)]
    assert songfacts.facts(tmp_path / "nothing.mid")["title"] == "nothing"


def test_song_page_api(tmp_path):
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    make_gp(config.SONGS_DIR / "tune.gp5")
    c = TestClient(app)
    f = c.get("/api/songs/tune.gp5/facts").json()
    assert f["searches"]["backing"] == "Test tune Nobody backing track" and f["video"] is None
    s = c.post("/api/songs/tune.gp5/sections", json=dict(key="Verse", state="solid")).json()
    assert s["mastery"] == 25 and s["sections"][1]["state"] == "solid"           # (0 + 75 + 0) / 3 of 100
    assert c.post("/api/songs/tune.gp5/video", json=dict(url="https://example.com/v")).json()["video"] == "https://example.com/v"
    assert c.post("/api/songs/tune.gp5/video", json=dict(url="nope")).json()["detail"]["code"] == "bad_url"
    assert next(x for x in c.get("/api/songs").json() if x["name"] == "tune.gp5")["readiness"] == 25
    assert c.get("/api/songs/missing.gp5/facts").status_code == 404


def test_setlists_with_tuning_warnings():
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    make_gp(config.SONGS_DIR / "dropd.gp5")
    c = TestClient(app)
    s = c.post("/api/setlists", json=dict(name="Friday")).json()
    assert c.post("/api/setlists", json=dict(name="friday")).json()["detail"]["code"] == "duplicate_name"
    assert c.post("/api/setlists", json=dict(name="  ")).json()["detail"]["code"] == "empty_name"
    items = [dict(kind="chart", id="01-em-am"), dict(kind="song", id="dropd.gp5"), dict(kind="chart", id="03-pop-in-g")]
    s = c.put(f"/api/setlists/{s['id']}", json=dict(items=items)).json()
    assert [w["index"] for w in s["warnings"]] == [1, 2]
    assert s["warnings"][0] == {"index": 1, "from": "standard", "to": "drop_d"}
    assert s["items"][0]["title"] and s["items"][1]["tuning"] == "drop_d"
    s = c.put(f"/api/setlists/{s['id']}", json=dict(items=[items[0], items[2], items[1]])).json()
    assert [w["index"] for w in s["warnings"]] == [2]                       # reordered: one retune at the end
    assert c.put(f"/api/setlists/{s['id']}", json=dict(items=[dict(kind="x", id="1")])).json()["detail"]["code"] == "bad_item"
    assert c.delete(f"/api/setlists/{s['id']}").json()["ok"]
    assert c.get(f"/api/setlists/{s['id']}").status_code == 404


def test_chart_readiness_and_tuning_header():
    from guitarr import catalog
    c = TestClient(app)
    c.post("/api/charts/25-song-form-aaba/sections", json=dict(key="A", state="ready"))
    row = next(x for x in c.get("/api/charts").json() if x["id"] == "25-song-form-aaba")
    assert row["readiness"] == 25 and row["tuning"] == "standard"
    assert catalog.parse_chart("tuning: Drop D\nD | G\n")["tuning"] == "drop_d"
    import pytest
    with pytest.raises(catalog.CatalogError):
        catalog.parse_chart("tuning: banjo\nD | G\n")
