"""judge-check: the chord judge measured on a folder of recordings (here, synthesized ones)."""
import json

import soundfile as sf

from guitarr import catalog, cli, judgecheck
from tests.test_learning import SR, synth_strums


def _strum(folder, asked, played, name):
    (folder / asked).mkdir(parents=True, exist_ok=True)
    chart = catalog.chart_from_chord(played)
    chart = dict(chart, bpm=60, bars=chart["bars"][:1], capo=0)
    sf.write(folder / asked / name, synth_strums(chart), SR)


def test_counts_false_mistakes_and_wrong_chords(tmp_path, capsys):
    _strum(tmp_path, "G", "G", "ok-1.wav")
    _strum(tmp_path, "Am", "Am", "ok-1.wav")
    _strum(tmp_path, "G", "A", "A-1.wav")                      # clearly wrong (Em shares two notes with G and can pass)
    _strum(tmp_path, "Am", "A", "A-1.wav")
    (tmp_path / "notachord").mkdir()
    r = judgecheck.run(tmp_path, log=lambda m: None)
    assert (r["files"], r["right"], r["false_mistakes"], r["wrong"], r["caught"], r["swaps"]) == (4, 2, 0, 2, 2, 1)
    assert r["swaps_caught"] == 1
    cli.main(["judge-check", str(tmp_path), "--json"])
    assert json.loads(capsys.readouterr().out.split("\n", 1)[1])["caught"] == 2
