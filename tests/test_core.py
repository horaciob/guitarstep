import numpy as np
import pytest

from guitarr.core import Grid


def test_grid_basic_4_4():
    g = Grid(np.arange(16) * 0.5, 4)  # 120 bpm
    assert g.bar_of(0.0) == (1, 1.0)
    assert g.bar_of(2.0) == (2, 1.0)
    assert g.bar_of(2.75) == (2, 2.5)
    assert g.bar_time(3) == pytest.approx(4.0)
    assert "bar   2 beat 2.50" in g.locate(2.75)


def test_grid_extrapolates_past_the_end_and_before_start():
    g = Grid(np.arange(8) * 0.5, 4)
    assert g.bar_of(10.0) == (6, 1.0)          # 20 beats later
    assert g.bar_time(10) == pytest.approx(18.0)
    bar, beat = g.bar_of(-0.5)                  # one beat before bar 1
    assert bar == 0 and beat == pytest.approx(4.0)


@pytest.mark.parametrize("beats", [[], [1.0]])
def test_grid_tiny_grids_dont_crash(beats):
    g = Grid(beats, 4)
    g.locate(3.0)
    g.bar_time(5)
    g.bar_of(-1)


def test_grid_time_signature_change():
    # one bar of 4/4, then 3/4
    beats = np.arange(13) * 0.5
    g = Grid(beats, 3, bar_starts=[0, 4, 7, 10])
    assert g.bar_of(2.0) == (2, 1.0)
    assert g.bar_of(3.5) == (3, 1.0)
    assert g.bar_of(5.0) == (4, 1.0)
    assert g.bar_of(6.5) == (5, 1.0)            # extrapolates with 3/4
    assert g.beats_in_bar(1) == 4 and g.beats_in_bar(2) == 3
    assert g.is_downbeat(4) and g.is_downbeat(7) and not g.is_downbeat(5)


def test_grid_from_bpm_has_no_length_limit():
    g = Grid.from_bpm(200, 0.0, 4, until=3600)   # one hour at 200 bpm > 4000 beats
    assert g.beats[-1] >= 3600
    assert g.bar_of(3000)[0] == int(3000 * 200 / 60 // 4) + 1
