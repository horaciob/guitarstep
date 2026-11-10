"""Setlists: songs and charts in the order you'll play them, stored in ~/.guitarr/setlists.json.

Each item is a chart (by id) or an uploaded song (by file name). When two items in a row need different
tunings, the setlist says so, so you can reorder or plan a retune.
"""
from __future__ import annotations

import json
import threading
import uuid

from . import catalog, config

_lock = threading.Lock()
MAX_ITEMS = 60


class SetlistError(ValueError):
    pass


def path():
    return config.HOME / "setlists.json"


def _read() -> list[dict]:
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _write(data: list[dict]) -> None:
    config.write_json(path(), data)


def all_lists() -> list[dict]:
    with _lock:
        return _read()


def create(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise SetlistError("empty_name")
    if len(name) > 80:
        raise SetlistError("long_name")
    with _lock:
        data = _read()
        if any(s["name"].casefold() == name.casefold() for s in data):
            raise SetlistError("duplicate_name")
        s = dict(id=uuid.uuid4().hex[:10], name=name, items=[])
        data.append(s)
        _write(data)
        return s


def get(sid: str) -> dict:
    with _lock:
        s = next((x for x in _read() if x["id"] == sid), None)
    if s is None:
        raise SetlistError("no_setlist")
    return s


def update(sid: str, items: list[dict] | None = None, name: str | None = None) -> dict:
    """Replaces the items (in order) and/or the name."""
    with _lock:
        data = _read()
        s = next((x for x in data if x["id"] == sid), None)
        if s is None:
            raise SetlistError("no_setlist")
        if name is not None:
            name = name.strip()
            if not name:
                raise SetlistError("empty_name")
            s["name"] = name[:80]
        if items is not None:
            clean = []
            for it in items[:MAX_ITEMS]:
                kind, ref = it.get("kind"), str(it.get("id", ""))
                if kind not in ("chart", "song") or not ref:
                    raise SetlistError("bad_item")
                clean.append(dict(kind=kind, id=ref))
            s["items"] = clean
        _write(data)
        return s


def delete(sid: str) -> None:
    with _lock:
        data = _read()
        if not any(x["id"] == sid for x in data):
            raise SetlistError("no_setlist")
        _write([x for x in data if x["id"] != sid])


def tuning_of(item: dict) -> str:
    """The tuning an item needs: a chart's `tuning:` header, a song file's own tuning, or standard."""
    if item["kind"] == "chart":
        try:
            return catalog.get_chart(item["id"]).get("tuning") or "standard"
        except catalog.CatalogError:
            return "standard"
    from . import songfacts

    p = config.SONGS_DIR / item["id"]
    return (songfacts.facts(p).get("tuning") if p.exists() else None) or "standard"


def warnings(items: list[dict]) -> list[dict]:
    """[{index, from, to}] for every item whose tuning differs from the one before it."""
    out, prev = [], None
    for i, it in enumerate(items):
        tun = tuning_of(it)
        if prev is not None and tun != prev:
            out.append(dict(index=i, **{"from": prev, "to": tun}))
        prev = tun
    return out
