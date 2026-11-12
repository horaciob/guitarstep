from guitarr import config, history


def test_config_roundtrip():
    config.update_audio(device="Scarlett 2i2 \"USB\"", channel=2, latency_ms=12.5)
    config.save_song_preset("my song.gp5", track="lead", start_bar=9, end_bar=12, speed=0.7)
    data = config.load()
    assert data["audio"] == {"device": 'Scarlett 2i2 "USB"', "channel": 2, "latency_ms": 12.5}
    assert config.song_preset("/another/path/my song.gp5") == {"track": "lead", "start_bar": 9,
                                                               "end_bar": 12, "speed": 0.7}


def _session(score, bars):
    return dict(kind="live", mode="tempo", speed=0.7, reference=dict(name="riff", path="/x/riff.mid", track=None),
                summary=dict(score=score), bars=bars)


def test_history_and_problem_bars():
    for k in range(3):
        history.save(_session(60 + 10 * k, [dict(bar=1, notes=8, errors=0, timing=0),
                                            dict(bar=2, notes=8, errors=4 - k, timing=1),
                                            dict(bar=3, notes=8, errors=1, timing=0)]),
                     section=dict(start_bar=1, end_bar=3))
    songs = history.songs()
    assert songs[0]["id"] == "riff" and songs[0]["sessions"] == 3 and songs[0]["last_score"] == 80
    sess = history.load_sessions("riff")
    pb = history.problem_bars(sess)
    assert [r["bar"] for r in pb] == [2, 3]
    cmd = history.suggest_command("riff", sess)
    assert "--start-bar 2 --end-bar 3" in cmd and "--trainer" in cmd


def test_json_is_written_whole_or_not_at_all(tmp_path, monkeypatch):
    from pathlib import Path

    from guitarr import config
    p = tmp_path / "sub" / "data.json"
    config.write_json(p, {"a": "ñ"})
    assert p.read_text(encoding="utf-8") == '{\n "a": "ñ"\n}'

    def boom(self, target):
        raise OSError("disk full")
    monkeypatch.setattr(Path, "replace", boom)
    try:
        config.write_json(p, {"a": "new"})
    except OSError:
        pass
    assert p.read_text(encoding="utf-8") == '{\n "a": "ñ"\n}'          # the old file is intact
    assert sorted(x.name for x in p.parent.iterdir()) == ["data.json"]   # and no temp file is left


def test_then_and_now_pairs_the_first_and_latest_takes():
    import numpy as np
    import soundfile as sf
    from fastapi.testclient import TestClient

    from guitarr import config, history
    from guitarr.gui.server import app

    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    ref = dict(name="Tune", path="/x/tune.mid", track=None)
    for k, score in enumerate((55, 70, 88)):
        take = config.TAKES_DIR / f"take-2026010{k + 1}-100000.wav"
        sf.write(take, np.zeros(8000, np.float32), 8000)
        history.save(dict(kind="live", mode="tempo", reference=ref, take=str(take), speed=0.8 + 0.1 * k,
                          summary=dict(score=score)))
    history.save(dict(kind="live", mode="wait", reference=ref, summary=dict(score=90)))      # no take: not paired
    h = TestClient(app).get(f"/api/history/{history.song_id('/x/tune.mid')}").json()
    tn = h["then_now"]
    assert tn["then"]["take"].endswith("01-100000.wav") and tn["now"]["take"].endswith("03-100000.wav")
    assert (tn["then"]["score"], tn["now"]["score"], tn["sessions"]) == (55, 88, 4)
    (config.TAKES_DIR / tn["then"]["take"]).unlink()                                           # deleted takes don't count
    (config.TAKES_DIR / "take-20260102-100000.wav").unlink()
    assert TestClient(app).get(f"/api/history/{history.song_id('/x/tune.mid')}").json()["then_now"] is None
