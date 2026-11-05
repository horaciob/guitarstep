"""Tone rig storage: the current rig and the user's presets, in ~/.guitarr/rig.json.

The rig itself (guitar voicing, pedals, amp, cabinet, mic, effects) runs in the browser with
Web Audio; this module only stores its JSON. The listener never hears the rig: grading
always uses the clean input.
"""
from __future__ import annotations

import json
import re
import uuid

from . import config

MAX_BYTES = 64_000       # one rig as JSON
MAX_PRESETS = 200
MAX_NAME = 60


class RigError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def path():
    return config.HOME / "rig.json"


def _read() -> dict:
    try:
        d = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("current", None)
    if not isinstance(d.get("presets"), list):
        d["presets"] = []
    return d


def _write(d: dict) -> None:
    config.HOME.mkdir(parents=True, exist_ok=True)
    tmp = path().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path())


def _check_rig(rig) -> dict:
    if not isinstance(rig, dict):
        raise RigError("bad_rig", "The rig must be an object")
    if len(json.dumps(rig)) > MAX_BYTES:
        raise RigError("rig_too_big", "The rig is too big")
    return rig


def get() -> dict:
    return _read()


def save_current(rig: dict) -> dict:
    d = _read()
    d["current"] = _check_rig(rig)
    _write(d)
    return d


def save_preset(name: str, rig: dict) -> dict:
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_NAME]
    if not name:
        raise RigError("bad_name", "The preset needs a name")
    _check_rig(rig)
    d = _read()
    same = next((p for p in d["presets"] if p["name"].lower() == name.lower()), None)
    if same:                         # saving with an existing name overwrites it
        same["rig"] = rig
        preset = same
    else:
        if len(d["presets"]) >= MAX_PRESETS:
            raise RigError("too_many_presets", "Too many presets: delete some first")
        preset = dict(id=uuid.uuid4().hex[:12], name=name, rig=rig)
        d["presets"].append(preset)
    _write(d)
    return preset


def delete_preset(pid: str) -> bool:
    d = _read()
    before = len(d["presets"])
    d["presets"] = [p for p in d["presets"] if p.get("id") != pid]
    if len(d["presets"]) == before:
        return False
    _write(d)
    return True
