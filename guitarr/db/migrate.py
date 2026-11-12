"""Ordered, forward-only schema migrations.

Each change to the database is a new file in migrations/ named NNNN_what_it_does.sql
(`guitarr db new what_it_does` creates the next one). `guitarr db migrate` applies the files
that haven't run yet, in number order, each in its own transaction, and records them in
schema_migrations with a checksum. Rules:

- never edit or renumber a migration that was applied somewhere: write a new one instead
  (an edited file is refused, since its checksum no longer matches);
- to undo a change, write a migration that reverses it.

Two processes migrating at once (several app containers starting) wait for each other through
an advisory lock, so every migration runs exactly once."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from ..errors import CodedError

DIR = Path(__file__).parent / "migrations"
NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
LOCK_ID = 7_301_224_015            # advisory lock key: "guitarr migrations"

TABLE = """CREATE TABLE IF NOT EXISTS schema_migrations (
    version    integer PRIMARY KEY,
    name       text NOT NULL,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


def discover(folder: Path = DIR) -> list[Migration]:
    out = []
    for p in sorted(folder.glob("*.sql")):
        m = NAME.match(p.name)
        if not m:
            raise CodedError("bad_migration_name", f"{p.name}: migrations are named NNNN_what_it_does.sql")
        out.append(Migration(int(m[1]), m[2], p))
    versions = [m.version for m in out]
    if len(set(versions)) != len(versions):
        raise CodedError("duplicate_migration", "Two migrations share a number")
    return out


def _applied(conn) -> dict[int, dict]:
    if conn.execute("SELECT to_regclass('schema_migrations') AS t").fetchone()["t"] is None:
        return {}                     # a new database: nothing applied yet
    return {r["version"]: r for r in conn.execute(
        "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version").fetchall()}


def _check(found: list[Migration], applied: dict[int, dict]) -> None:
    by_version = {m.version: m for m in found}
    for v, row in applied.items():
        m = by_version.get(v)
        if m is None:
            raise CodedError("missing_migration", f"Migration {v:04d}_{row['name']} was applied but its file is gone")
        if m.checksum != row["checksum"]:
            raise CodedError("edited_migration", f"{m.path.name} changed after it was applied: write a new migration instead")


def _connect(url: str):
    from psycopg.rows import dict_row
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def status(url: str, folder: Path = DIR) -> list[dict]:
    """Every migration with applied_at (None: pending)."""
    found = discover(folder)
    with _connect(url) as conn:
        applied = _applied(conn)
    _check(found, applied)
    return [dict(version=m.version, name=m.name,
                 applied_at=applied[m.version]["applied_at"] if m.version in applied else None) for m in found]


def pending(url: str, folder: Path = DIR) -> list[Migration]:
    found = {m.version: m for m in discover(folder)}
    return [found[s["version"]] for s in status(url, folder) if s["applied_at"] is None]


def migrate(url: str, folder: Path = DIR, log=print) -> list[Migration]:
    """Applies the pending migrations in order; returns the ones it applied."""
    found = discover(folder)
    done = []
    with _connect(url) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            conn.execute(TABLE)           # after the lock: two first runs would race to create it
            applied = _applied(conn)      # read after the lock: another process may have just migrated
            _check(found, applied)
            for m in found:
                if m.version in applied:
                    continue
                with conn.transaction():  # the file and its record land together, or not at all
                    conn.execute(m.sql)
                    conn.execute("INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                                 (m.version, m.name, m.checksum))
                log(f"applied {m.path.name}")
                done.append(m)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    return done


def new(name: str, folder: Path = DIR) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise CodedError("bad_migration_name", "Give the migration a name, e.g. add_setlists")
    found = discover(folder)
    p = folder / f"{(found[-1].version + 1 if found else 1):04d}_{slug}.sql"
    p.write_text(f"-- {slug.replace('_', ' ')}\n", encoding="utf-8")
    return p
