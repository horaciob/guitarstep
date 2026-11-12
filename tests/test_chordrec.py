"""A chord chart from a recording (synthesized strums with known chords)."""
import numpy as np
import soundfile as sf

from guitarr import catalog, chordrec
from tests.test_learning import SR, synth_strums


def test_smoothing_ignores_a_one_beat_blip():
    names, T = chordrec.templates()
    g, c = T[names.index("G")], T[names.index("C")]
    beats = np.array([g, g, c * 0.6 + g * 0.5, g, c, c, c, c]).T                 # beat 3 leans C for a moment
    got = chordrec.beat_chords(beats, np.ones(8))
    assert got == ["G"] * 4 + ["C"] * 4


def test_the_bar_starts_where_the_chords_change():
    assert chordrec.downbeat(["Em", "Em", "G", "G", "G", "G", "D", "D", "D", "D"]) == 2


def test_bars_and_halves():
    assert chordrec.bars_of(["G"] * 4 + ["C", "C", "D", "D"]) == [["G"], ["C", "D"]]
    assert chordrec.bars_of(["G", "G", "G", "Em"]) == [["G"]]


def test_chart_from_a_strummed_recording(tmp_path):
    prog = ["G", "D", "Em", "C"] * 2
    chart = dict(id="x", title="x", bpm=90, beats_per_bar=4, capo=0,
                 bars=[dict(chord=c, beats=4, frets=catalog.get_chord(c)["frets"]) for c in prog])
    y = synth_strums(chart, lead=0.0)
    wav = tmp_path / "song.wav"
    sf.write(wav, y, SR)
    r = chordrec.from_audio(wav, title="Song")
    assert 80 <= r["bpm"] <= 100 or 160 <= r["bpm"] <= 200
    parsed = catalog.parse_chart(r["text"])
    heard = [b["chord"] for b in parsed["bars"]]
    hits = sum(any(h == p for h in heard[max(0, i - 1):i + 2]) for i, p in enumerate(prog))
    assert hits >= 6, heard                                                       # most bars right (a draft)


def test_api_upload_and_song(tmp_path):
    from fastapi.testclient import TestClient

    from guitarr import config
    from guitarr.gui.server import app

    prog = ["Am", "F", "C", "G"] * 2
    chart = dict(id="x", title="x", bpm=110, beats_per_bar=4, capo=0,
                 bars=[dict(chord=c, beats=4, frets=catalog.get_chord(c)["frets"]) for c in prog])
    wav = tmp_path / "jam.wav"
    sf.write(wav, synth_strums(chart, lead=0.5), SR)
    c = TestClient(app)
    r = c.post("/api/charts/from-audio", files=dict(file=("jam.wav", wav.read_bytes(), "audio/wav"))).json()
    assert r["text"].startswith("title: jam\n") and c.post("/api/charts/validate", json=dict(text=r["text"])).json()["chart"]
    assert c.post("/api/charts/from-audio", files=dict(file=("x.txt", b"hi", "text/plain"))).json()["detail"]["code"] == "bad_format"
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    (config.SONGS_DIR / "jam.wav").write_bytes(wav.read_bytes())
    assert "Am" in c.post("/api/songs/jam.wav/chart").json()["chords"]
