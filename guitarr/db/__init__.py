"""Postgres for the web service (several users). The local app doesn't use it.

The service mode is on when GUITARR_DATABASE_URL is set, e.g.
postgresql://guitarr:secret@db:5432/guitarr. Schema changes are numbered SQL files in
migrations/, applied in order by `guitarr db migrate` (see migrate.py)."""
from __future__ import annotations

import os
import threading

_pool = None
_lock = threading.Lock()


def url() -> str | None:
    return os.environ.get("GUITARR_DATABASE_URL") or None


def enabled() -> bool:
    return url() is not None


def pool():
    """The shared connection pool (opened on first use). `with pool().connection() as conn:` commits
    at the end of the block, or rolls back on an exception."""
    global _pool
    with _lock:
        if _pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            _pool = ConnectionPool(url(), min_size=1, max_size=int(os.environ.get("GUITARR_DB_POOL", "10")),
                                   kwargs=dict(row_factory=dict_row), open=True)
        return _pool


def close() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
