"""Backup and restore of your guitarr data (~/.guitarr) as a zip file.

What goes in: settings, progress, practice plan, tone rig presets, history, your songs and
charts, and the impulse responses you uploaded. Recorded takes are optional (they can be big).
The transcription cache is never included: it is rebuilt when needed.

Restoring replaces the files that are in the backup and keeps a copy of what was there
first, in ~/.guitarr/backups/.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from . import __version__, config

FILES = ("config.toml", "progress.json", "plan.json", "rig.json")
DIRS = ("history", "songs", "charts", "irs")
OPTIONAL_DIRS = ("takes",)
MANIFEST = "guitarr-backup.json"
MAX_BYTES = 2 * 1024 ** 3          # unpacked size limit on restore
MAX_ENTRIES = 20_000


class BackupError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _members(takes: bool):
    home = config.HOME
    for name in FILES:
        p = home / name
        if p.is_file():
            yield p, name
    for d in DIRS + (OPTIONAL_DIRS if takes else ()):
        root = home / d
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    yield p, p.relative_to(home).as_posix()


def create(takes: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        names = []
        for p, arc in _members(takes):
            z.write(p, arc)
            names.append(arc)
        z.writestr(MANIFEST, json.dumps(dict(app="guitarr", version=__version__, takes=takes,
                                             created=datetime.now().isoformat(timespec="seconds"),
                                             files=len(names)), indent=1))
    return buf.getvalue()


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
        for info in entries:
            target = home / Path(*PurePosixPath(info.filename).parts)
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
    return path
