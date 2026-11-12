"""Teacher assignments: a setlist shared as a file. A teacher exports a setlist with a note ("this week: the verse
at 80 BPM"); the student imports the file and gets the same setlist, with the note, and the teacher's own charts
(their text travels inside the file). Uploaded song files don't travel: the import says which ones to ask for.
Progress goes back the other way with the weekly report (print or PDF)."""
from __future__ import annotations

from . import catalog, setlists

VERSION = 1
MAX_NOTE = 2000


class AssignmentError(ValueError):
    pass


def export(sid: str, note: str = "") -> dict:
    s = setlists.get(sid)
    items = []
    for it in s["items"]:
        row = dict(kind=it["kind"], id=it["id"])
        if it["kind"] == "chart":
            try:
                text, mine = catalog.chart_text(it["id"])
            except catalog.CatalogError:
                continue
            if mine:                                   # a chart the student won't have: send its text
                row["text"] = text
        items.append(row)
    return dict(guitarr_assignment=VERSION, name=s["name"], note=(note or s.get("note") or "")[:MAX_NOTE], items=items)


def import_(data: dict) -> dict:
    """Creates the setlist (and the charts it carries). Returns {setlist, charts: [ids], missing_songs: [names]}."""
    if not isinstance(data, dict) or data.get("guitarr_assignment") != VERSION or not isinstance(data.get("items"), list):
        raise AssignmentError("not_assignment")
    from . import config

    items, charts, missing = [], [], []
    for it in data["items"][:setlists.MAX_ITEMS]:
        kind, ref = it.get("kind"), str(it.get("id") or "")
        if kind == "chart" and it.get("text"):
            try:
                existing, mine = catalog.chart_text(ref)
            except catalog.CatalogError:
                existing, mine = None, False
            if existing is None or (mine and existing.strip() != str(it["text"]).strip()):
                cid = ref if existing is None else f"{ref}-teacher"
                try:
                    ref = catalog.save_chart(str(it["text"]), catalog.slug(cid))["id"]
                except catalog.CatalogError as e:
                    raise AssignmentError(f"bad_chart:{e}") from e
                charts.append(ref)
            items.append(dict(kind="chart", id=ref))
        elif kind == "chart":
            try:
                catalog.get_chart(ref)
            except catalog.CatalogError:
                continue                                 # a built-in chart this version doesn't have
            items.append(dict(kind="chart", id=ref))
        elif kind == "song":
            items.append(dict(kind="song", id=ref))
            if not (config.SONGS_DIR / ref).exists():
                missing.append(ref)
    base = str(data.get("name") or "Assignment").strip()[:70] or "Assignment"
    names = {s["name"].casefold() for s in setlists.all_lists()}
    name, k = base, 2
    while name.casefold() in names:
        name, k = f"{base} ({k})", k + 1
    s = setlists.create(name)
    s = setlists.update(s["id"], items=items, note=str(data.get("note") or "")[:MAX_NOTE])
    return dict(setlist=s, charts=charts, missing_songs=missing)
