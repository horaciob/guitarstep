"""Background jobs for the web service: slow work (transcribing a recording with basic-pitch, separating
the guitar with Demucs, analyzing a take) runs in a worker, not in the request.

A request that needs one enqueues it and answers 202 {"job": {...}, "retry": bool}; the page waits for it at
/api/jobs/<id> (lib/ui.js api() does it for every call) and gets the job's result, or sends its request again
when `retry` (the job only prepared what the request needs). Workers: `guitarr worker` (any number of them, a
job is claimed with FOR UPDATE SKIP LOCKED) or threads of the app itself (GUITARR_WORKERS, 1 by default; 0 when
a worker service runs). A job runs as its user (config.use_user).

    GUITARR_JOBS_PER_USER (3): jobs one user can have waiting or running at once
"""
from __future__ import annotations

import contextvars
import os
import threading
import time

from . import config, db
from .errors import CodedError

HANDLERS: dict = {}
_running: contextvars.ContextVar[bool] = contextvars.ContextVar("guitarr_job", default=False)
STALE_MINUTES = 30        # a running job older than this lost its worker: it's tried again
MAX_ATTEMPTS = 2
KEEP_DAYS = 7             # finished jobs are deleted after this


def per_user() -> int:
    return int(os.environ.get("GUITARR_JOBS_PER_USER") or 3)


def handler(kind: str):
    """Registers fn(args) -> result (JSON) as the work of a kind of job."""
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


class JobPending(Exception):
    """Raised by a request that has to wait for a job: the server answers 202 with it."""

    def __init__(self, job: dict, retry: bool = False):
        super().__init__(job["kind"])
        self.job, self.retry = job, retry


def in_job() -> bool:
    """True inside a job (where the slow work is done, not deferred to another job)."""
    return _running.get()


def public(row: dict) -> dict:
    return dict(id=row["id"], kind=row["kind"], status=row["status"], result=row["result"], error=row["error"])


def enqueue(kind: str, args: dict) -> dict:
    """The current user's job of this kind with these arguments: the one waiting or running already, or a new one."""
    from psycopg.types.json import Jsonb
    user = config.user_id()
    with db.pool().connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user,))      # one enqueue per user at a time
        row = conn.execute("SELECT * FROM jobs WHERE user_id = %s AND kind = %s AND args = %s "
                           "AND status IN ('queued', 'running')", (user, kind, Jsonb(args))).fetchone()
        if row:
            return public(row)
        n = conn.execute("SELECT count(*) AS n FROM jobs WHERE user_id = %s AND status IN ('queued', 'running')",
                         (user,)).fetchone()["n"]
        if n >= per_user():
            raise CodedError("too_many_jobs", "Wait for what's being prepared to finish first")
        row = conn.execute("INSERT INTO jobs (user_id, kind, args) VALUES (%s, %s, %s) RETURNING *",
                           (user, kind, Jsonb(args))).fetchone()
    return public(row)


def get(job_id: int) -> dict | None:
    """One of the current user's jobs."""
    with db.pool().connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s AND user_id = %s", (job_id, config.user_id())).fetchone()
    return row and public(row)


def _claim(conn) -> dict | None:
    conn.execute("UPDATE jobs SET status = 'queued' WHERE status = 'running' AND attempts < %s "
                 "AND started_at < now() - make_interval(mins => %s)", (MAX_ATTEMPTS, STALE_MINUTES))
    conn.execute("UPDATE jobs SET status = 'failed', finished_at = now(), "
                 "error = '{\"code\": \"job_failed\", \"message\": \"The job stopped halfway\"}' "
                 "WHERE status = 'running' AND started_at < now() - make_interval(mins => %s)", (STALE_MINUTES,))
    return conn.execute(
        "UPDATE jobs SET status = 'running', started_at = now(), attempts = attempts + 1 WHERE id = "
        "(SELECT id FROM jobs WHERE status = 'queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *").fetchone()


def run_next() -> bool:
    """Runs one waiting job; False when there was none."""
    from psycopg.types.json import Jsonb
    with db.pool().connection() as conn:
        row = _claim(conn)
        if row is None:
            conn.execute("DELETE FROM jobs WHERE finished_at < now() - make_interval(days => %s)", (KEEP_DAYS,))
            return False
    result = error = None
    try:
        fn = HANDLERS.get(row["kind"])
        if fn is None:
            raise CodedError("job_failed", f"Unknown job: {row['kind']}")
        tok = _running.set(True)
        try:
            with config.use_user(str(row["user_id"])):
                result = fn(row["args"])
        finally:
            _running.reset(tok)
    except CodedError as e:
        error = dict(code=e.code, message=str(e))
    except Exception as e:  # noqa: BLE001 - the job fails, the worker goes on
        detail = getattr(e, "detail", None)          # an HTTPException from a shared helper
        error = detail if isinstance(detail, dict) else dict(code="job_failed", message=str(e) or type(e).__name__)
    with db.pool().connection() as conn:
        conn.execute("UPDATE jobs SET status = %s, result = %s, error = %s, finished_at = now() WHERE id = %s",
                     ("failed" if error else "done", None if result is None else Jsonb(result),
                      error and Jsonb(error), row["id"]))
    return True


def work(stop: threading.Event | None = None, idle_s: float = 1.0) -> None:
    """Runs jobs until `stop` is set."""
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            busy = run_next()
        except Exception as e:  # noqa: BLE001 - e.g. the database restarting: try again in a moment
            print(f"[guitarr] worker: {e}", flush=True)
            busy = False
        if not busy:
            stop.wait(idle_s)


def start_threads(n: int | None = None) -> None:
    n = int(os.environ.get("GUITARR_WORKERS", "1")) if n is None else n
    for _ in range(n):
        threading.Thread(target=work, daemon=True, name="guitarr-worker").start()


def wait(job_id: int, timeout_s: float = 30) -> dict | None:
    """The job once it finished (tests)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        j = get(job_id)
        if j and j["status"] in ("done", "failed"):
            return j
        time.sleep(0.05)
    return get(job_id)
