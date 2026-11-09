"""Tunings and handedness."""
from fastapi.testclient import TestClient

from guitarr import config
from guitarr.core import TUNINGS, Note
from guitarr.gui.server import app
from guitarr.reference import assign_tab
from guitarr.tuner import Tuner


class _Src:
    sr = 48000


def test_tunings_are_highest_string_first():
    for name, t in TUNINGS.items():
        assert t == sorted(t, reverse=True) or name in ("open_g", "open_d", "dadgad"), name
        assert len(t) in (4, 6, 7)
    assert TUNINGS["drop_d"][-1] == 38 and TUNINGS["seven_string"][-1] == 35


def test_instrument_settings_round_trip():
    assert config.instrument() == dict(tuning="standard", left_handed=False, tab_low_on_top=True)
    config.save_instrument(tuning="drop_d", left_handed=True)
    config.update_audio(latency_ms=5.0)                       # other sections keep it
    assert config.instrument() == dict(tuning="drop_d", left_handed=True, tab_low_on_top=True)
    assert config.instrument_tuning() == TUNINGS["drop_d"]


def test_tab_follows_the_tuning():
    low_d = [Note(0, 1, 38, 0.8)]
    assign_tab(low_d, TUNINGS["standard"])
    assert low_d[0].string is None                            # below a standard low E
    low_d = [Note(0, 1, 38, 0.8)]
    assign_tab(low_d, TUNINGS["drop_d"])
    assert (low_d[0].string, low_d[0].fret) == (6, 0)
    b = [Note(0, 1, 35, 0.8)]
    assign_tab(b, TUNINGS["seven_string"])
    assert (b[0].string, b[0].fret) == (7, 0)


def test_tuner_strings_follow_the_tuning():
    tn = Tuner(_Src(), tuning=TUNINGS["bass_4"])
    assert tn.tuning == [43, 38, 33, 28] and tn.fmin < 41.2          # low E of a bass (41.2 Hz)
    tn = Tuner(_Src(), tuning=TUNINGS["drop_d"])
    assert tn.tuning.index(38) + 1 == 6


def test_instrument_api():
    c = TestClient(app)
    r = c.get("/api/instrument").json()
    assert r["tuning"] == "standard" and r["strings"] == TUNINGS["standard"] and "dadgad" in r["tunings"]
    r = c.put("/api/instrument", json=dict(tuning="open_g", left_handed=True)).json()
    assert r["strings"] == TUNINGS["open_g"] and r["left_handed"] is True
    assert c.put("/api/instrument", json=dict(tuning="banjo")).json()["detail"]["code"] == "bad_tuning"
