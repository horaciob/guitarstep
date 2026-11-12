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

import contextlib
import contextvars
import json
import os
import threading
import tomllib
from pathlib import Path

# The data folder. Alone, the app keeps everything in it. As a web service each signed-in user
# gets a folder of their own (BASE/users/<id>, chosen per request by use_home), and the
# transcription cache (keyed by file hash) stays shared in BASE/cache.
BASE = Path(os.environ.get("GUITARR_HOME", "~/.guitarr")).expanduser()
CACHE_DIR = BASE / "cache"
_home: contextvars.ContextVar[Path | None] = contextvars.ContextVar("guitarr_home", default=None)
_UNDER_HOME = dict(CONFIG_PATH="config.toml", SONGS_DIR="songs", TAKES_DIR="takes", HISTORY_DIR="history")


def __getattr__(name: str) -> Path:
    """config.HOME, CONFIG_PATH, SONGS_DIR, TAKES_DIR and HISTORY_DIR: the current user's."""
    if name == "HOME":
        return _home.get() or BASE
    if name in _UNDER_HOME:
        return (_home.get() or BASE) / _UNDER_HOME[name]
    raise AttributeError(name)


def user_home(user_id: str) -> Path:
    return BASE / "users" / user_id


@contextlib.contextmanager
def use_home(path: Path | None):
    """Inside the block, config.HOME (and what's under it) is `path`. Threads started inside it
    keep it only through in_this_context()."""
    tok = _home.set(path)
    try:
        yield
    finally:
        _home.reset(tok)


def in_this_context(fn):
    """`fn` wrapped to run with the current user's folder, for a thread or a timer."""
    ctx = contextvars.copy_context()
    return lambda *a, **k: ctx.run(fn, *a, **k)

def write_text_atomic(path: Path, text: str) -> None:
    """Writes the whole file or nothing: a temp file beside it (one per writer), then a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def write_json(path: Path, data) -> None:
    """Saves data as readable JSON, atomically (see write_text_atomic)."""
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=1))


INSTRUMENT_DEFAULTS = dict(tuning="standard", left_handed=False, tab_low_on_top=True)   # tab: 6th string on the top line
AUDIO_KEYS = ("device", "channel", "output_device", "samplerate", "latency_ms", "gate_db", "sensitivity", "hum_hz")
SONG_KEYS = ("track", "transpose", "start_bar", "end_bar", "mode", "speed", "bpm", "first_beat",
             "beats_per_bar")


def load() -> dict:
    try:
        with open(__getattr__("CONFIG_PATH"), "rb") as f:
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
    __getattr__("HOME").mkdir(parents=True, exist_ok=True)
    lines = _table("audio", data.get("audio", {}))
    if data.get("instrument"):
        lines += _table("instrument", data["instrument"])
    if data.get("latency"):
        lines += _table("latency", data["latency"])
    if data.get("reminder"):
        lines += _table("reminder", data["reminder"])
    for song, opts in sorted(data.get("songs", {}).items()):
        lines += _table(f"songs.{_val(song)}", opts)
    write_text_atomic(__getattr__("CONFIG_PATH"), "\n".join(lines))


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
