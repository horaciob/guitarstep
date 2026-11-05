"""Text tab and MusicXML import."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from guitarr.core import TUNINGS
from guitarr.gui.server import app
from guitarr.importers import ImportError_, load_musicxml, looks_like_tab, parse_tab
from guitarr.reference import RefOptions, load_reference

TAB = """Intro (tab by me)
e|-----0---------|-------------|
B|---1---1-------|-----3-------|
G|-2-------2-----|---2---2-----|
D|---------------|-0---------12|
A|-3-------------|-------------|
E|---------------|-------------|
"""


def test_tab_notes_strings_and_frets():
    assert looks_like_tab(TAB) and not looks_like_tab("just some\nlyrics here\n")
    ref = parse_tab(TAB, bpm=60)
    t0 = min(n.start for n in ref.notes)
    first = [(n.string, n.fret, n.pitch) for n in ref.notes if n.start == t0]
    assert sorted(first) == [(3, 2, 57), (5, 3, 48)]                # C on A string + A on G string
    assert ref.tuning == TUNINGS["standard"]
    twelve = [n for n in ref.notes if n.fret == 12]
    assert len(twelve) == 1 and twelve[0].pitch == 50 + 12           # two-digit fret on D
    # two bars of 4 beats at 60 bpm → 8 s
    assert max(n.start for n in ref.notes) < 8 and ref.notes[-1].start >= 4


def test_drop_d_and_seven_string_tabs():
    drop = "\n".join(["E|---|", "B|---|", "G|---|", "D|---|", "A|---|", "D|-0-|"])
    assert parse_tab(drop).notes[0].pitch == 38
    seven = "\n".join(["e|---|", "B|---|", "G|---|", "D|---|", "A|---|", "E|---|", "B|-0-|"])
    n = parse_tab(seven).notes[0]
    assert n.pitch == 35 and n.string == 7


def test_bad_tabs():
    with pytest.raises(ImportError_):
        parse_tab("hello")
    with pytest.raises(ImportError_):
        parse_tab("\n".join(["e|---|", "B|---|", "G|---|", "D|---|", "A|---|", "E|---|"]))   # no notes


XML = """<?xml version="1.0"?>
<score-partwise version="3.1"><work><work-title>Little tune</work-title></work>
<part-list><score-part id="P1"><part-name>Guitar</part-name></score-part></part-list>
<part id="P1">
 <measure number="1">
  <attributes><divisions>2</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
  <direction><sound tempo="120"/></direction>
  <note><pitch><step>E</step><octave>4</octave></pitch><duration>2</duration>
    <notations><technical><string>1</string><fret>0</fret></technical></notations></note>
  <note><pitch><step>G</step><octave>3</octave></pitch><duration>2</duration></note>
  <note><chord/><pitch><step>B</step><alter>-1</alter><octave>3</octave></pitch><duration>2</duration></note>
  <note><rest/><duration>2</duration></note>
 </measure>
 <measure number="2">
  <note><pitch><step>A</step><octave>3</octave></pitch><duration>4</duration><tie type="start"/></note>
  <note><pitch><step>A</step><octave>3</octave></pitch><duration>2</duration><tie type="stop"/></note>
 </measure>
</part></score-partwise>"""


def test_musicxml(tmp_path):
    p = tmp_path / "tune.musicxml"
    p.write_text(XML)
    ref = load_musicxml(p)
    assert ref.name == "Little tune" and ref.grid.bpb == 3
    got = [(round(n.start, 2), round(n.end, 2), n.pitch, n.string) for n in ref.notes]
    assert got == [(0.0, 0.5, 64, 1), (0.5, 1.0, 55, None), (0.5, 1.0, 58, None), (1.5, 3.0, 57, None)]  # tie joined


def test_mxl_and_entities_are_handled(tmp_path):
    p = tmp_path / "tune.mxl"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
        z.writestr("score.xml", XML)
    p.write_bytes(buf.getvalue())
    assert len(load_musicxml(p).notes) == 4
    bomb = tmp_path / "bomb.xml"
    bomb.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><score-partwise/>')
    with pytest.raises(ImportError_):
        load_musicxml(bomb)


def test_references_and_upload(tmp_path):
    p = tmp_path / "t.musicxml"
    p.write_text(XML)
    ref = load_reference(RefOptions(path=p), log=lambda m: None)
    assert all(n.string for n in ref.notes)                       # fingered for the instrument
    c = TestClient(app)
    r = c.post("/api/songs", files=dict(file=("riff.txt", TAB.encode())))
    assert r.json()["name"] == "riff.tab"
    pv = c.post("/api/preview", json=dict(song="riff.tab")).json()
    assert len(pv["notes"]) > 5 and all(n["string"] for n in pv["notes"])
    assert c.post("/api/songs", files=dict(file=("notes.txt", b"buy milk"))).json()["detail"]["code"] == "bad_format"
    assert c.post("/api/songs", files=dict(file=("t.musicxml", XML.encode()))).status_code == 200
