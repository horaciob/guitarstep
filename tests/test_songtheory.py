"""A song's theory: key, chords per bar, the chords of the key, outside chords and the main progression."""
from fastapi.testclient import TestClient

from guitarr import catalog, config, songtheory
from guitarr.reference import RefOptions, load_reference


def _chart(cid):
    return songtheory.analyze(load_reference(RefOptions(chart=catalog.get_chart(cid)), log=lambda m: None))


def test_pop_in_g_is_i_v_vi_iv():
    a = _chart("03-pop-in-g")
    assert (a["key"]["root"], a["key"]["mode"]) == ("G", "major")
    assert a["progression"]["chords"] == ["G", "D", "Em", "C"] and a["progression"]["romans"] == ["I", "V", "vi", "IV"]
    assert [c["bars"] for c in a["field"]] == [2, 0, 0, 2, 2, 2, 0] and a["outside"] == []
    bar1 = a["bars"][0]
    assert bar1["job"] == "tonic" and bar1["resting"]["degree"] == "1" and bar1["scales"]


def test_relative_keys_and_the_blues_are_told_apart_by_their_chords():
    assert (_chart("10-andalusian-cadence")["key"]["root"], _chart("10-andalusian-cadence")["key"]["mode"]) == ("A", "minor")
    blues = _chart("15-eight-bar-blues-a")
    assert blues["key"]["root"] == "A" and {u["chord"] for u in blues["outside"]} >= {"A7", "D7"}   # I7 and IV7 aren't diatonic
    assert _chart("11-ii-v-i")["key"]["root"] == "C"


def test_building_blocks():
    hist = [0.0] * 12
    for pc in (7, 11, 2, 5):                                   # G B D F
        hist[pc] = 1.0
    assert songtheory.detect_chord(hist) == dict(root=7, quality="7", fit=1.0)
    assert songtheory.roman_of(10, "maj", 0, "major") == "♭VII"
    assert songtheory.roman_of(11, "dim", 9, "minor") == "ii°"
    assert songtheory.roman_of(8, "maj", 9, "minor") == "♯VII"
    assert songtheory.find_progression(["C", "G", "Am", "F"] * 2 + ["C"]) == dict(start=0, length=4, count=2)
    assert songtheory.find_progression(["C"] * 8) is None


def test_song_theory_endpoint(tmp_path):
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=25, name="Guitar")
    chords = [[43, 47, 50, 55], [50, 54, 57, 62], [40, 47, 52, 55], [48, 52, 55, 60]] * 2     # G D Em C, twice
    for bar, ch in enumerate(chords):
        for p in ch:
            inst.notes.append(pretty_midi.Note(velocity=90, pitch=p, start=bar * 2.0, end=bar * 2.0 + 1.9))
    pm.instruments.append(inst)
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    pm.write(str(config.SONGS_DIR / "loop.mid"))
    from guitarr.gui.server import app
    a = TestClient(app).get("/api/songs/loop.mid/theory").json()
    assert a["key"] == dict(root="G", mode="major", score=a["key"]["score"])
    assert a["progression"]["romans"] == ["I", "V", "vi", "IV"]
