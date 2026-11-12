"""Chord sheets (chords over lyrics, ChordPro) → charts with lyrics."""
import pytest
from fastapi.testclient import TestClient

from guitarr import catalog, chordsheet
from guitarr.catalog import CatalogError
from guitarr.gui.server import app

SHEET = """Sweet Song
[Verse 1]
G           D            Em      C
Here I am on the road again, and again
G     D

Chorus:
[C]Take me [G]home to the [Am]place I [F/A]belong
"""


def test_chords_over_lyrics_and_chordpro():
    r = chordsheet.convert(SHEET)
    assert r["title"] == "Sweet Song" and r["bars"] == 10 and r["sections"] == 2
    c = catalog.parse_chart(r["text"])
    got = [(b["chord"], b.get("lyric"), b.get("section")) for b in c["bars"]]
    assert got[:4] == [("G", "Here I am", "Verse 1"), ("D", "on the road", None), ("Em", "again, and", None), ("C", "again", None)]
    assert got[4:6] == [("G", None, None), ("D", None, None)]                       # chords with no lyric line
    assert got[6] == ("C", "Take me", "Chorus") and got[9] == ("F/A", "belong", None)


def test_a_chord_in_the_middle_of_a_word_takes_the_word():
    assert chordsheet._split_lyric("Hello beautiful world", [0, 9]) == ["Hello", "beautiful world"]


def test_chordpro_directives_and_no_chords():
    r = chordsheet.convert("{title: Song}\n{artist: Someone}\n[Am]la la [E7]lo")
    assert r["text"].startswith("title: Song\nartist: Someone\n") and "> la la | lo" in r["text"]
    with pytest.raises(ValueError):
        chordsheet.convert("just words\nand more words")


def test_lyrics_lines_in_the_chart_format():
    c = catalog.parse_chart("G | D C | Em\n> one | two | three\n")
    assert [b.get("lyric") for b in c["bars"]] == ["one", "two", None, "three"]
    with pytest.raises(CatalogError, match="need a line of chords"):
        catalog.parse_chart("> words first\nG | D\n")
    with pytest.raises(CatalogError, match="3 lyric cells for 2 bars"):
        catalog.parse_chart("G | D\n> a | b | c\n")


def test_import_api():
    c = TestClient(app)
    r = c.post("/api/charts/import-text", json=dict(text=SHEET)).json()
    assert r["bars"] == 10 and c.post("/api/charts/validate", json=dict(text=r["text"])).json()["chart"]
    assert c.post("/api/charts/import-text", json=dict(text="no chords here")).json()["error"]["code"] == "no_chords"
