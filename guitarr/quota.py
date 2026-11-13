"""How much each user of the web service can keep: the files in their folder (songs, takes, impulse
responses, backups' safety copies). The local app has no limit.

    GUITARR_QUOTA_MB (1000)
"""
from __future__ import annotations

import os

from . import config, store
from .errors import CodedError

MB = 1024 * 1024


def limit_bytes() -> int:
    return int(float(os.environ.get("GUITARR_QUOTA_MB") or 1000) * MB)


def used_bytes() -> int:
    home = config.HOME
    if not home.is_dir():
        return 0
    return sum(p.stat().st_size for p in home.rglob("*") if p.is_file() and not p.is_symlink())


def usage() -> dict | None:
    """{used_mb, quota_mb} as a web service, else None."""
    if not store.in_db():
        return None
    return dict(used_mb=round(used_bytes() / MB, 1), quota_mb=round(limit_bytes() / MB))


def check(adding: int = 0) -> None:
    """Refuses to keep `adding` more bytes over the quota (web service only)."""
    if store.in_db() and used_bytes() + max(0, adding) > limit_bytes():
        raise CodedError("quota_exceeded", f"Your space is full ({round(limit_bytes() / MB)} MB): "
                                           "delete takes or songs you don't need")
