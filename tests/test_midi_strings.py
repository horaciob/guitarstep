"""MIDI with one channel per string (Songsterr's export): the exact string and fret survive the import."""
import mido

from guitarr.reference import RefOptions, list_tracks, load_reference, string_groups


def _songsterr_midi(path, drop_d=False):
    mid = mido.MidiFile(ticks_per_beat=480)
    tempo = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=500000, time=0)])
    mid.tracks.append(tempo)
    for name, notes in (("Rhythm Guitar", [(1, 64), (0, 64), (5, 38 if drop_d else 40)]), ("Lead", [(0, 76), (1, 71), (2, 67), (3, 62)])):
        head = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0), mido.Message("program_change", program=29, channel=0, time=0)])
        mid.tracks.append(head)
        for ch in range(6):                                  # one track per string, channel = string (0 = highest)
            tr = mido.MidiTrack()
            k = 0
            for i, (c, pitch) in enumerate(notes):
                if c != ch:
                    continue
                tr.append(mido.Message("note_on", channel=ch, note=pitch, velocity=90, time=i * 480 - k))
                tr.append(mido.Message("note_off", channel=ch, note=pitch, velocity=0, time=400))
                k = i * 480 + 400
            if not len(tr):
                tr.append(mido.Message("note_on", channel=ch, note=[64, 59, 55, 50, 45, 40][ch], velocity=60, time=4000))
                tr.append(mido.Message("note_off", channel=ch, note=[64, 59, 55, 50, 45, 40][ch], velocity=0, time=100))
            mid.tracks.append(tr)
    drums = mido.MidiTrack([mido.Message("note_on", channel=9, note=36, velocity=90, time=0), mido.Message("note_off", channel=9, note=36, time=100)])
    mid.tracks.append(drums)
    mid.save(str(path))
    return path


def test_each_channel_is_a_string(tmp_path):
    p = _songsterr_midi(tmp_path / "song.mid")
    groups = string_groups(p)
    assert [g["name"] for g in groups] == ["Rhythm Guitar", "Lead"]
    ref = load_reference(RefOptions(path=p, track="Rhythm"), log=lambda m: None)
    first = sorted(ref.notes, key=lambda n: n.start)[:3]
    assert [(n.string, n.fret) for n in first] == [(2, 5), (1, 0), (6, 0)]   # E on the B string stays at fret 5
    assert ref.track == "Rhythm Guitar" and ref.tuning == [64, 59, 55, 50, 45, 40]
    assert [t["name"] for t in list_tracks(p)] == ["Rhythm Guitar", "Lead"]


def test_a_lower_string_means_a_drop_tuning(tmp_path):
    ref = load_reference(RefOptions(path=_songsterr_midi(tmp_path / "d.mid", drop_d=True), track="0"), log=lambda m: None)
    assert ref.tuning[5] == 38 and any(n.string == 6 and n.fret == 0 and n.pitch == 38 for n in ref.notes)


def test_ordinary_midi_is_unchanged(tmp_path):
    import pretty_midi
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=25, name="Guitar")
    inst.notes.append(pretty_midi.Note(velocity=90, pitch=64, start=0, end=0.5))
    pm.instruments.append(inst)
    pm.write(str(tmp_path / "plain.mid"))
    assert string_groups(tmp_path / "plain.mid") == []
    ref = load_reference(RefOptions(path=tmp_path / "plain.mid"), log=lambda m: None)
    n = ref.notes[0]                                     # placed by the usual heuristic
    assert n.string and ref.tuning[n.string - 1] + n.fret == 64
