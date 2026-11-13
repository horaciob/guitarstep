"""Where a user's documents live: settings, progress, practice plan, tone rig and setlists.

The local app keeps each one as a file in config.HOME (config.toml, progress.json…). As a web service
(a database and a signed-in user, see config.use_user) they are rows of `user_documents`; a document a
user still has as a file (written before the database kept them) is moved in the first time it's read.
"""
from __future__ import annotations

import contextvars
import json
import threading
import tomllib

from . import config, db

FILES = dict(config="config.toml", progress="progress.json", plan="plan.json", rig="rig.json",
             setlists="setlists.json")


# the connection holding a document's lock (Lock), by document name: reads and writes inside go through it
_held: contextvars.ContextVar[dict | None] = contextvars.ContextVar("guitarr_store_held", default=None)


class Lock:
    """Around a read-modify-write of one document (`with _lock: d = _read(); …; _write(d)`): a thread lock, and
    as a web service also a lock on that user's document in Postgres, held by one transaction, because the app
    and the workers are different processes writing the same documents."""

    def __init__(self, name: str):
        self.name = name
        self._thread = threading.Lock()
        self._local = threading.local()

    def __enter__(self):
        self._thread.acquire()
        entry = None
        try:
            if in_db():
                cm = db.pool().connection()
                conn = cm.__enter__()
                try:
                    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{config.user_id()}:{self.name}",))
                except BaseException:
                    cm.__exit__(None, None, None)
                    raise
                entry = (cm, _held.set({**(_held.get() or {}), self.name: conn}))
        except BaseException:
            self._thread.release()
            raise
        self._local.entry = entry
        return self

    def __exit__(self, *exc):
        entry, self._local.entry = self._local.entry, None
        try:
            if entry:
                cm, tok = entry
                _held.reset(tok)
                cm.__exit__(*exc)            # commits, or rolls back on an error
        finally:
            self._thread.release()
        return False


def _connection(name: str):
    """The connection holding `name`'s lock, else a new one from the pool (as a context manager)."""
    conn = (_held.get() or {}).get(name)
    if conn is None:
        return db.pool().connection()
    from contextlib import nullcontext
    return nullcontext(conn)


def in_db() -> bool:
    """True when the current user's data is in the database (the web service)."""
    return config.user_id() is not None and db.enabled()


def path(name: str):
    return config.HOME / FILES[name]


def _from_file(name: str):
    p = path(name)
    try:
        if p.suffix == ".toml":
            with open(p, "rb") as f:
                return tomllib.load(f)
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read(name: str):
    """The document, or None when there's none yet (or it can't be read)."""
    if not in_db():
        return _from_file(name)
    with _connection(name) as conn:
        row = conn.execute("SELECT data FROM user_documents WHERE user_id = %s AND name = %s",
                           (config.user_id(), name)).fetchone()
    if row is not None:
        return row["data"]
    old = _from_file(name)
    if old is not None:           # kept as a file before: move it in
        write(name, old)
        path(name).rename(path(name).with_name(path(name).name + ".imported"))
    return old


def write(name: str, data) -> None:
    if name == "config":          # the same values either way: what a TOML file can hold (no None)
        text = config.to_toml(data)
        if not in_db():
            config.write_text_atomic(path(name), text)
            return
        data = tomllib.loads(text)
    elif not in_db():
        config.write_json(path(name), data)
        return
    from psycopg.types.json import Jsonb
    with _connection(name) as conn:
        conn.execute("INSERT INTO user_documents (user_id, name, data) VALUES (%s, %s, %s) "
                     "ON CONFLICT (user_id, name) DO UPDATE SET data = EXCLUDED.data, updated_at = now()",
                     (config.user_id(), name, Jsonb(data)))
