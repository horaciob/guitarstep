from guitarr import config, history


def test_config_roundtrip():
    config.update_audio(device="Scarlett 2i2 \"USB\"", channel=2, latency_ms=12.5)
    config.save_song_preset("mi canción.gp5", track="lead", start_bar=9, end_bar=12, speed=0.7)
    data = config.load()
    assert data["audio"] == {"device": 'Scarlett 2i2 "USB"', "channel": 2, "latency_ms": 12.5}
    assert config.song_preset("/otra/ruta/mi canción.gp5") == {"track": "lead", "start_bar": 9,
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
