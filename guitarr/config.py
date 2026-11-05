"""Data paths and persistent settings (~/.guitarr/config.toml).

    [audio]
    device = "Scarlett 2i2"
    channel = 1
    latency_ms = 12.5

    [songs."song.mid"]
    track = "lead"
    transpose = 0
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

HOME = Path(os.environ.get("GUITARR_HOME", "~/.guitarr")).expanduser()
CONFIG_PATH = HOME / "config.toml"
CACHE_DIR = HOME / "cache"
SONGS_DIR = HOME / "songs"
TAKES_DIR = HOME / "takes"
HISTORY_DIR = HOME / "history"

INSTRUMENT_DEFAULTS = dict(tuning="standard", left_handed=False)
AUDIO_KEYS = ("device", "channel", "output_device", "samplerate", "latency_ms", "gate_db", "sensitivity", "hum_hz")
SONG_KEYS = ("track", "transpose", "start_bar", "end_bar", "mode", "speed", "bpm", "first_beat",
             "beats_per_bar")


def load() -> dict:
    try:
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        data = {}
    data.setdefault("audio", {})
    data.setdefault("songs", {})
    return data


def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _table(name: str, d: dict) -> list[str]:
    lines = [f"[{name}]"]
    lines += [f"{k} = {_val(v)}" for k, v in d.items() if v is not None and not isinstance(v, dict)]
    return lines + [""]


def save(data: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    lines = _table("audio", data.get("audio", {}))
    if data.get("instrument"):
        lines += _table("instrument", data["instrument"])
    if data.get("reminder"):
        lines += _table("reminder", data["reminder"])
    for song, opts in sorted(data.get("songs", {}).items()):
        lines += _table(f"songs.{_val(song)}", opts)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def update_audio(**kw) -> dict:
    data = load()
    data["audio"].update({k: v for k, v in kw.items() if k in AUDIO_KEYS and v is not None})
    save(data)
    return data["audio"]


def instrument() -> dict:
    """Your tuning and handedness (used by the tuners, tablature and diagrams)."""
    return {**INSTRUMENT_DEFAULTS, **load().get("instrument", {})}


def instrument_tuning() -> list[int]:
    from .core import tuning_of
    return tuning_of(instrument()["tuning"])


def save_instrument(**kw) -> dict:
    data = load()
    data["instrument"] = {**INSTRUMENT_DEFAULTS, **data.get("instrument", {}),
                          **{k: v for k, v in kw.items() if k in INSTRUMENT_DEFAULTS and v is not None}}
    save(data)
    return data["instrument"]


def song_key(path: Path | str) -> str:
    return Path(path).name


def song_preset(path: Path | str) -> dict:
    return load()["songs"].get(song_key(path), {})


def save_song_preset(path: Path | str, **kw) -> dict:
    data = load()
    preset = data["songs"].setdefault(song_key(path), {})
    preset.update({k: v for k, v in kw.items() if k in SONG_KEYS and v is not None})
    save(data)
    return preset
