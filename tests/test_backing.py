"""Bass & drums backing for chord charts."""
import numpy as np
import pytest

from guitarr import catalog
from guitarr.audio_io import BackingSounds
from guitarr.follow import backing_track, chord_root, group_events
from guitarr.reference import RefOptions, load_reference


@pytest.mark.parametrize("name,pc", [("C", 0), ("Am", 9), ("F#m7", 6), ("Bb", 10), ("Dsus4", 2), ("C/G", 7),
                                     ("Fmaj7", 5), ("E5", 4), (None, None), ("x", None)])
def test_chord_root(name, pc):
    assert chord_root(name) == pc


def test_backing_follows_the_chart():
    ref = load_reference(RefOptions(chart=catalog.get_chart("01-em-am")), log=lambda m: None)
    events = group_events(ref.notes)
    g = ref.grid
    bar0 = g.bar_time(g.bar_index(events[0].time))
    end = g.bar_time(g.bar_index(events[-1].time) + 1)
    track = backing_track(events, g, bar0, end, bar_start=10.0, speed=1.0)
    assert track == sorted(track) and track[0][0] == pytest.approx(10.0)
    kicks = [t for t, s in track if s == "kick"]
    snares = [t for t, s in track if s == "snare"]
    hats = [t for t, s in track if s == "hat"]
    bass = [(t, s) for t, s in track if s.startswith("bass:")]
    assert len(hats) == 2 * (len(kicks) + len(snares))             # eighth notes
    assert len(bass) == len(kicks)                                  # bass on the strong beats
    roots = {int(s.split(":")[1]) % 12 for _, s in bass}
    assert roots == {4, 9}                                          # Em and Am → E and A
    assert all(28 <= int(s.split(":")[1]) <= 39 for _, s in bass)
    slow = backing_track(events, g, bar0, end, bar_start=10.0, speed=0.5)
    assert slow[-1][0] - 10.0 == pytest.approx(2 * (track[-1][0] - 10.0), rel=0.05)   # half speed, twice as long


def test_backing_sounds_are_finite_and_cached():
    s = BackingSounds(48000)
    for key in ("kick", "snare", "hat", "bass:28", "bass:39"):
        w = s.get(key)
        assert w.dtype == np.float32 and len(w) > 100 and np.isfinite(w).all() and np.abs(w).max() < 1
        assert s.get(key) is w


def test_the_capo_moves_the_bass():
    ref = load_reference(RefOptions(chart=catalog.get_chart("01-em-am")), log=lambda m: None)
    events = group_events(ref.notes)
    g = ref.grid
    bar0, end = g.bar_time(0), g.bar_time(g.bar_index(events[-1].time) + 1)
    plain = {int(s[5:]) % 12 for _, s in backing_track(events, g, bar0, end, 0.0, 1.0) if s.startswith("bass:")}
    capo2 = {int(s[5:]) % 12 for _, s in backing_track(events, g, bar0, end, 0.0, 1.0, capo=2) if s.startswith("bass:")}
    assert capo2 == {(pc + 2) % 12 for pc in plain}
