import numpy as np
import pretty_midi
import pytest

from guitarr import reference
from guitarr.core import Note
from guitarr.reference import (HARMONIC_INTERVALS, RefOptions, ReferenceError, assign_tab, clean_notes,
                               list_tracks, load_reference)


def clean_notes_slow(notes, win=0.05):
    """Implementación original O(n³), para comparar."""
    drop = set()
    for i, n in enumerate(notes):
        for j, m in enumerate(notes):
            if i == j or abs(m.start - n.start) > win or m.amp <= n.amp:
                continue
            if (n.pitch - m.pitch) in HARMONIC_INTERVALS and n.amp < 0.65 * m.amp:
                drop.add(i)
                break
            rang = any(p.pitch == n.pitch and abs(p.end - n.start) < 0.08 and p.start < n.start - win
                       for p in notes)
            if rang:
                drop.add(i)
                break
    return [n for i, n in enumerate(notes) if i not in drop]


def test_clean_notes_matches_original():
    rng = np.random.default_rng(0)
    for _ in range(20):
        notes = []
        t = 0.0
        for _ in range(80):
            t += rng.choice([0.0, 0.01, 0.12, 0.25])
            p = int(rng.integers(40, 76))
            notes.append(Note(t, t + rng.uniform(0.05, 0.6), p, float(rng.uniform(0.2, 1))))
            if rng.random() < 0.3:  # armónico débil
                notes.append(Note(t + 0.01, t + 0.3, p + 12, float(rng.uniform(0.1, 0.4))))
        notes.sort(key=lambda n: (n.start, n.pitch))
        fast = [(n.start, n.pitch) for n in clean_notes(notes)]
        slow = [(n.start, n.pitch) for n in clean_notes_slow(notes)]
        assert fast == slow


def test_clean_notes_is_fast():
    import time

    notes = [Note(i * 0.1, i * 0.1 + 0.3, 40 + i % 30, 0.5 + (i % 7) / 20) for i in range(3000)]
    t = time.perf_counter()
    clean_notes(notes)
    assert time.perf_counter() - t < 2.0


def test_assign_tab():
    notes = [Note(0, 1, 40), Note(1, 2, 45), Note(2, 3, 64), Note(3, 4, 45), Note(3, 4, 52), Note(3, 4, 57)]
    assign_tab(notes)
    assert (notes[0].string, notes[0].fret) == (6, 0)
    chord = notes[3:]
    assert len({n.string for n in chord}) == 3          # cuerdas distintas
    for n in notes:
        assert n.string is not None and 0 <= n.fret <= 22


def _midi_with_meter_change(path):
    pm = pretty_midi.PrettyMIDI(initial_tempo=120)
    pm.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0), pretty_midi.TimeSignature(3, 4, 2.0)]
    inst = pretty_midi.Instrument(program=25, name="lead")
    for k in range(10):
        inst.notes.append(pretty_midi.Note(100, 60 + k % 5, k * 0.5, k * 0.5 + 0.4))
    bass = pretty_midi.Instrument(program=33, name="bajo")
    bass.notes.append(pretty_midi.Note(100, 40, 0, 1))
    pm.instruments += [bass, inst]
    pm.write(str(path))


def test_load_midi_time_signatures_and_tracks(tmp_path):
    p = tmp_path / "x.mid"
    _midi_with_meter_change(p)
    ref = load_reference(RefOptions(p), log=lambda m: None)  # elige la guitarra
    assert ref.track == "lead"
    g = ref.grid
    assert g.bar_of(2.0) == (2, 1.0)
    assert g.bar_of(3.5) == (3, 1.0)       # 3/4 desde el compás 2
    assert all(n.string for n in ref.notes)
    sec = load_reference(RefOptions(p, start_bar=3, end_bar=3), log=lambda m: None)
    assert [round(n.start, 2) for n in sec.notes] == [3.5, 4.0, 4.5]
    assert [t["name"] for t in list_tracks(p)] == ["bajo", "lead"]
    with pytest.raises(ReferenceError):
        load_reference(RefOptions(p, track="violin"))


def test_load_guitar_pro(tmp_path):
    import guitarpro
    from guitarpro import models as m

    song = m.Song(tempo=120)
    tr = song.tracks[0]
    tr.name = "Guitarra"
    voice = tr.measures[0].voices[0]
    start = tr.measures[0].start
    for k, (s, f) in enumerate([(6, 0), (5, 2), (4, 2), (3, 1)]):
        b = m.Beat(voice, start=start + k * 960, status=m.BeatStatus.normal, duration=m.Duration(value=4))
        b.notes.append(m.Note(b, value=f, string=s, type=m.NoteType.normal))
        voice.beats.append(b)
    p = tmp_path / "riff.gp5"
    guitarpro.write(song, str(p))
    ref = load_reference(RefOptions(p), log=lambda m: None)
    assert [n.pitch for n in ref.notes] == [40, 47, 52, 56]
    assert [(n.string, n.fret) for n in ref.notes] == [(6, 0), (5, 2), (4, 2), (3, 1)]
    assert [round(n.start, 3) for n in ref.notes] == [0.0, 0.5, 1.0, 1.5]
    assert ref.grid.bar_of(1.0) == (1, 3.0)


def test_transcription_cache(demo_dir, monkeypatch):
    first = reference.transcribe(demo_dir / "toma.wav")

    def boom():
        raise AssertionError("no debería volver a correr basic-pitch")

    monkeypatch.setattr(reference, "_quiet_import_basic_pitch", boom)
    again = reference.transcribe(demo_dir / "toma.wav")
    assert [(n.start, n.pitch) for n in again] == [(n.start, n.pitch) for n in first]
