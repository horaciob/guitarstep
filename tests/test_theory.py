import pytest

from guitarr import theory as th


def names(sc):
    return [s["note"] for s in sc]


def test_spelling_follows_the_key():
    assert names(th.scale("F#", "major")) == ["F#", "G#", "A#", "B", "C#", "D#", "E#"]
    assert names(th.scale("Gb", "major")) == ["Gb", "Ab", "Bb", "Cb", "Db", "Eb", "F"]
    assert names(th.scale("C", "natural_minor")) == ["C", "D", "Eb", "F", "G", "Ab", "Bb"]
    assert names(th.scale("A", "harmonic_minor"))[-1] == "G#"
    assert th.transpose("C", "m3") == "Eb" and th.transpose("B", "A4") == "E#"
    assert th.relative_minor("Eb") == "C"


def test_every_scale_in_every_key_is_spelled_with_one_letter_per_step():
    for key in ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb"]:
        for name in ("major", "natural_minor", "harmonic_minor", "melodic_minor", "dorian", "lydian", "mixolydian"):
            sc = names(th.scale(key, name))
            assert len({n[0] for n in sc}) == 7, (key, name, sc)


def test_modes_and_other_scales():
    assert names(th.scale("D", "dorian")) == ["D", "E", "F", "G", "A", "B", "C"]
    assert names(th.scale("C", "altered")) == ["C", "Db", "D#", "E", "F#", "Ab", "Bb"]
    assert [s["degree"] for s in th.scale("C", "lydian")][3] == "#4"
    assert len(th.scale("C", "half_whole")) == 8 and len(th.scale("C", "whole_tone")) == 6


def test_intervals():
    assert th.interval_name(45, 49) == "M3"
    assert th.interval_name(45, 51) == "A4"
    assert th.interval_name(40, 52) == "P8"


def test_chords_parse_and_spell():
    assert [t["note"] for t in th.chord("Bbm7b5")["tones"]] == ["Bb", "Db", "Fb", "Ab"]
    assert [t["note"] for t in th.chord("G7#9")["tones"]] == ["G", "B", "D", "F", "A#"]
    assert th.parse_chord("C/E")["bass"] == "E"
    assert th.parse_chord("Cø")["quality"] == "m7b5"
    with pytest.raises(th.TheoryError):
        th.parse_chord("H7")


def test_name_chord_from_pitches():
    assert th.name_chord([48, 52, 55])[0] == "C"                 # C E G
    assert th.name_chord([52, 55, 60])[0] == "C/E"               # first inversion
    assert th.name_chord([43, 47, 50, 53])[0] == "G7"
    assert "Am7" in th.name_chord([45, 48, 52, 55])              # same notes as C6
    assert th.name_chord([]) == []


def test_harmonize_major_and_minor():
    tri = th.harmonize("C", "major", "triads")
    assert [c["roman"] for c in tri] == ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
    sev = th.harmonize("G", "major", "sevenths")
    assert [c["symbol"] for c in sev] == ["Gmaj7", "Am7", "Bm7", "Cmaj7", "D7", "Em7", "F#m7b5"]
    assert sev[6]["roman"] == "viiø7"
    hm = th.harmonize("A", "harmonic_minor", "sevenths")
    assert hm[4]["symbol"] == "E7" and hm[6]["symbol"] == "G#dim7"
    nin = th.harmonize("C", "major", "ninths")
    assert nin[0]["symbol"] == "Cmaj9" and nin[2]["symbol"] == "Em7"   # iii has a b9: stays a seventh


def test_scale_paths_are_playable_and_rising():
    run = th.scale_path("G", "major", 2, 5)
    assert run[0][2] % 12 == 7 and run[-1][2] == run[0][2] + 12
    assert all(b[2] > a[2] for a, b in zip(run, run[1:]))
    assert all(2 <= f <= 5 for _, f, _ in run)
    one = th.scale_path("A", "major", 5, 17, string=5)
    assert {s for s, _, _ in one} == {5}
    nps = th.scale_path("G", "major", 3, 15, nps=3)
    assert [s for s, _, _ in nps[:6]] == [6, 6, 6, 5, 5, 5]
    ud = th.scale_path("C", "major", 7, 10, direction="updown")
    assert ud[0] == ud[-1]


def test_arpeggio_path():
    run = th.arpeggio_path("Cmaj7", 7, 10)
    assert {p % 12 for _, _, p in run} == {0, 4, 7, 11}


def test_voicings_sound_the_chord():
    for sym, kind in [("C", "triad"), ("Am", "triad"), ("Cmaj7", "drop2"), ("G7", "drop3"), ("Dm7", "shell"), ("Bm7b5", "drop2")]:
        vs = th.voicings(sym, kind)
        assert vs, (sym, kind)
        want = {t["pc"] for t in th.chord(sym)["tones"]}
        for v in vs:
            got = {p % 12 for p in th.shape_pitches(v["frets"])}
            assert got <= want and len(got) >= 3, (sym, kind, v)
            pressed = [f for f in v["frets"] if f > 0]
            assert not pressed or max(pressed) - min(pressed) <= 3


def test_triad_inversions_by_string_set():
    vs = [v for v in th.voicings("C", "triad") if v["strings"] == "123"]
    assert {v["inversion"] for v in vs} == {0, 1, 2}
    first = next(v for v in vs if v["inversion"] == 1)
    assert th.shape_pitches(first["frets"])[0] % 12 == 4           # E in the bass of the set


def test_voice_leading_moves_little():
    vl = th.voice_lead(["Dm7", "G7", "Cmaj7"], "drop2", sets=("1234",))
    moves = [th._moved(th.shape_pitches(a["frets"]), th.shape_pitches(b["frets"])) for a, b in zip(vl, vl[1:])]
    assert all(m <= 4 for m in moves), moves
    gt = th.guide_tones(["Dm7", "G7", "Cmaj7"])
    assert [g["order"] for g in gt][0] != [g["order"] for g in gt][1]   # the voices swap places
