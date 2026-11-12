"""Groove: timing per part of the beat, and how even the attack is."""
from guitarr import groove
from guitarr.core import Grid

G = Grid([i * 0.5 for i in range(64)])          # 120 bpm: a beat every 0.5 s


def test_position():
    assert groove.position(G, 1.0) == "beat"
    assert groove.position(G, 1.25) == "and"
    assert groove.position(G, 1.125) == "sixteenth"
    assert groove.position(G, 1.0 + 0.5 / 3) == "triplet"
    assert groove.position(G, 1.08) == "other"


def test_late_on_the_and_only():
    hits = [(i * 0.5, 0.0) for i in range(8)] + [(i * 0.5 + 0.25, 0.035) for i in range(8)]
    rows = {r["pos"]: r for r in groove.timing_by_position(G, hits)}
    assert rows["beat"]["tend"] == "on_time" and rows["and"]["tend"] == "late" and rows["and"]["mean_ms"] == 35
    assert groove.tip(list(rows.values())) == dict(pos="and", tend="late", ms=35)


def test_too_few_notes_say_nothing():
    assert groove.timing_by_position(G, [(0.0, 0.05)] * 3) == []
    assert groove.tip([]) is None
    assert groove.dynamics(G, [(0.0, 0.5)] * 3) is None


def test_weak_upstrokes():
    notes = [(i * 0.5, 0.8) for i in range(8)] + [(i * 0.5 + 0.25, 0.4) for i in range(8)]
    d = groove.dynamics(G, notes)
    assert d["code"] == "off_softer" and d["offbeat_db"] == -6.0


def test_even_and_uneven():
    assert groove.dynamics(G, [(i * 0.5, 0.6) for i in range(10)])["code"] == "even"
    uneven = [(i * 0.5, 0.2 if i % 3 else 0.9) for i in range(12)]
    assert groove.dynamics(G, uneven)["code"] == "uneven"
