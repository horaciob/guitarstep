"""The web service's admin page: who uses it, how much space they take, how the jobs are doing, and
blocking an account. Admins are the emails in GUITARR_ADMINS (comma separated)."""
from __future__ import annotations

import os

from . import config, db
from .errors import CodedError
from .quota import MB


def admins() -> set[str]:
    return {e.strip().lower() for e in (os.environ.get("GUITARR_ADMINS") or "").split(",") if e.strip()}


def is_admin(user: dict | None) -> bool:
    return bool(user) and user["email"].lower() in admins()


def _folder_bytes(user_id: str) -> int:
    home = config.user_home(user_id)
    return sum(p.stat().st_size for p in home.rglob("*") if p.is_file() and not p.is_symlink()) if home.is_dir() else 0


def overview() -> dict:
    with db.pool().connection() as conn:
        users = conn.execute(
            "SELECT u.id::text AS id, u.email, u.created_at, u.last_login, u.blocked_at, "
            "(SELECT count(*) FROM practice_sessions p WHERE p.user_id = u.id) AS sessions, "
            "(SELECT max(s.last_seen) FROM sessions s WHERE s.user_id = u.id) AS last_seen "
            "FROM users u ORDER BY u.created_at").fetchall()
        week = conn.execute("SELECT count(*) AS n, count(DISTINCT user_id) AS users FROM practice_sessions "
                            "WHERE played_at > now() - interval '7 days'").fetchone()
        jobs = {r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM jobs GROUP BY status")}
        failed = conn.execute(
            "SELECT j.id, j.kind, u.email, j.error, j.finished_at FROM jobs j JOIN users u ON u.id = j.user_id "
            "WHERE j.status = 'failed' ORDER BY j.finished_at DESC LIMIT 20").fetchall()
    rows = [dict(id=u["id"], email=u["email"], created_at=u["created_at"].isoformat(),
                 last_seen=(u["last_seen"] or u["last_login"]) and (u["last_seen"] or u["last_login"]).isoformat(),
                 blocked=u["blocked_at"] is not None, sessions=u["sessions"],
                 space_mb=round(_folder_bytes(u["id"]) / MB, 1)) for u in users]
    return dict(users=rows, totals=dict(users=len(rows), blocked=sum(r["blocked"] for r in rows),
                                        space_mb=round(sum(r["space_mb"] for r in rows), 1),
                                        sessions_week=week["n"], active_week=week["users"]),
                jobs=dict(queued=jobs.get("queued", 0), running=jobs.get("running", 0), done=jobs.get("done", 0),
                          failed=jobs.get("failed", 0)),
                failed=[dict(id=f["id"], kind=f["kind"], email=f["email"], error=f["error"],
                             at=f["finished_at"] and f["finished_at"].isoformat()) for f in failed])


def block(user_id: str, blocked: bool) -> None:
    """A blocked account can't sign in, and is signed out everywhere."""
    if user_id == config.user_id():
        raise CodedError("block_self", "You can't block your own account")
    with db.pool().connection() as conn:
        row = conn.execute("UPDATE users SET blocked_at = CASE WHEN %s THEN coalesce(blocked_at, now()) END "
                           "WHERE id = %s RETURNING id", (blocked, user_id)).fetchone()
        if row is None:
            raise CodedError("no_user", "No such account")
        if blocked:
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
