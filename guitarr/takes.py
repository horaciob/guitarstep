"""Recorded takes in ~/.guitarr/takes: how much room they use, and clearing old ones.

Every listening session keeps what you played as a WAV, so the folder only grows. Nothing is
deleted on its own: you choose to clear takes older than some days from Settings.
"""
from __future__ import annotations

import time

from . import config, takeclick
from .errors import CodedError

DAY = 86400
AGES = (7, 30, 90, 0)          # days; 0 means every take


def _files():
    d = config.TAKES_DIR
    return sorted(d.glob("*.wav")) if d.is_dir() else []


def usage(now: float | None = None) -> dict:
    now = time.time() if now is None else now
    rows = [(p.stat().st_mtime, p.stat().st_size) for p in _files()]
    older = {str(days): dict(count=sum(1 for m, _ in rows if now - m > days * DAY),
                             bytes=sum(s for m, s in rows if now - m > days * DAY)) for days in AGES}
    return dict(count=len(rows), bytes=sum(s for _, s in rows), older=older)


def cleanup(days, now: float | None = None) -> dict:
    """Deletes takes (and their click files) older than `days`; 0 deletes them all."""
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = None
    if days not in AGES:
        raise CodedError("bad_days", "Choose how old the takes to delete are")
    now = time.time() if now is None else now
    deleted = freed = 0
    for p in _files():
        st = p.stat()
        if now - st.st_mtime <= days * DAY:
            continue
        freed += st.st_size
        p.unlink(missing_ok=True)
        takeclick.click_path(p).unlink(missing_ok=True)
        deleted += 1
    return dict(deleted=deleted, freed=freed, **usage(now))
