"""Backup and restore of your guitarr data (~/.guitarr) as a zip file.

What goes in: settings, progress, practice plan, tone rig presets, history, your songs and
charts, and the impulse responses you uploaded. Recorded takes are optional (they can be big).
The transcription cache is never included: it is rebuilt when needed.

Restoring replaces the files that are in the backup and keeps a copy of what was there
first, in ~/.guitarr/backups/. The zip is the same for the local app and the web service (where
settings, progress, history and charts are in the database), so a backup moves between them.
"""
from __future__ import annotations

import io
import json
import tomllib
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from . import __version__, catalog, config, history, store
from .errors import CodedError

FILES = tuple(store.FILES.values())       # documents (store.py)
DIRS = ("history", "songs", "charts", "irs")
DISK_DIRS = ("songs", "irs")              # files in your folder either way
OPTIONAL_DIRS = ("takes",)
MANIFEST = "guitarr-backup.json"
MAX_BYTES = 2 * 1024 ** 3          # unpacked size limit on restore
MAX_ENTRIES = 20_000


class BackupError(CodedError):
    pass


def _dump(data, toml: bool = False) -> bytes:
    return (config.to_toml(data) if toml else json.dumps(data, ensure_ascii=False, indent=1)).encode()


def _members(takes: bool):
    """(name in the zip, bytes or a file)."""
    for name, file in store.FILES.items():
        data = store.read(name)
        if data is not None:
            yield file, _dump(data, file.endswith(".toml"))
    for sid, name, data in history.export():
        yield f"history/{sid}/{name}", _dump(data)
    for cid, text in catalog.user_charts().items():
        yield f"charts/{cid}.txt", text.encode()
    home = config.HOME
    for d in DISK_DIRS + (OPTIONAL_DIRS if takes else ()):
        root = home / d
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    yield p.relative_to(home).as_posix(), p


def create(takes: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        names = []
        for arc, src in _members(takes):
            if isinstance(src, bytes):
                z.writestr(arc, src)
            else:
                z.write(src, arc)
            names.append(arc)
        z.writestr(MANIFEST, json.dumps(dict(app="guitarr", version=__version__, takes=takes,
                                             created=datetime.now().isoformat(timespec="seconds"),
                                             files=len(names)), indent=1))
    return buf.getvalue()


KEEP_SAFETY = 3


def filename() -> str:
    return f"guitarr-backup-{datetime.now():%Y-%m-%d}.zip"


def _allowed(name: str) -> bool:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not p.parts or "\\" in name:
        return False
    if len(p.parts) == 1:
        return p.name in FILES
    return p.parts[0] in DIRS + OPTIONAL_DIRS


def restore(data: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BackupError("bad_backup", "That file is not a guitarr backup") from None
    with z:
        if MANIFEST not in z.namelist():
            raise BackupError("bad_backup", "That file is not a guitarr backup")
        entries = [i for i in z.infolist() if not i.is_dir() and i.filename != MANIFEST]
        if len(entries) > MAX_ENTRIES or sum(i.file_size for i in entries) > MAX_BYTES:
            raise BackupError("backup_too_big", "The backup is too big")
        bad = [i.filename for i in entries if not _allowed(i.filename)]
        if bad:
            raise BackupError("bad_backup", f"Unexpected file in the backup: {bad[0]}")
        safety = _safety_copy()
        home = config.HOME
        docs = {file: name for name, file in store.FILES.items()}
        for info in entries:
            parts = PurePosixPath(info.filename).parts
            if parts[0] not in DISK_DIRS + OPTIONAL_DIRS:          # documents, history, charts
                raw = z.read(info)
                try:
                    if len(parts) == 1:
                        text = raw.decode("utf-8")
                        store.write(docs[parts[0]], tomllib.loads(text) if parts[0].endswith(".toml") else json.loads(text))
                    elif parts[0] == "history" and len(parts) == 3:
                        history.restore_session(parts[1], parts[2], json.loads(raw))
                    elif parts[0] == "charts" and len(parts) == 2 and parts[1].endswith(".txt"):
                        catalog.restore_chart(parts[1][:-4], raw.decode("utf-8"))
                    else:
                        raise ValueError(info.filename)
                except (ValueError, UnicodeDecodeError) as e:      # JSON and TOML errors are ValueErrors
                    raise BackupError("bad_backup", f"Unreadable file in the backup: {info.filename}") from e
                continue
            target = home / Path(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".restoring")
            with z.open(info) as src, open(tmp, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            tmp.replace(target)
    return dict(restored=len(entries), safety_copy=safety.name if safety else None)


def _safety_copy() -> Path | None:
    """What you had before restoring, in ~/.guitarr/backups/ (takes included)."""
    if not any(True for _ in _members(True)):
        return None
    folder = config.HOME / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"before-restore-{datetime.now():%Y-%m-%d-%H%M%S}.zip"
    path.write_bytes(create(takes=True))
    for old in sorted(folder.glob("before-restore-*.zip"))[:-KEEP_SAFETY]:   # they hold every take: keep the last few
        old.unlink(missing_ok=True)
    return path
