"""Classes, in the web service: a teacher invites students with a link. A student in a class shares their
weekly report (practice time, songs and scores, XP and skills: report.week) with that teacher, and gets
the setlists the teacher sends (assignments: the same content as an assignment file, see assignment.py).
Either side can end it at any time; then nothing is shared anymore.
"""
from __future__ import annotations

import hashlib
import os
import secrets

from . import assignment, config, db, report
from .errors import CodedError

INVITE_DAYS = 14
MAX_NOTE = assignment.MAX_NOTE


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _me() -> str:
    return config.user_id()


def invite(base_url: str) -> dict:
    """A link for students to join your class (it works for INVITE_DAYS days, for anyone who has it)."""
    code = secrets.token_urlsafe(12)
    with db.pool().connection() as conn:
        conn.execute("INSERT INTO class_invites (code_hash, teacher_id, expires_at) "
                     "VALUES (%s, %s, now() + make_interval(days => %s))", (_hash(code), _me(), INVITE_DAYS))
    base = (os.environ.get("GUITARR_PUBLIC_URL") or base_url).rstrip("/")
    return dict(code=code, url=f"{base}/#/class?join={code}", days=INVITE_DAYS)


def _teacher_of(conn, code: str) -> dict:
    row = conn.execute("SELECT u.id::text AS id, u.email FROM class_invites i JOIN users u ON u.id = i.teacher_id "
                       "WHERE i.code_hash = %s AND i.expires_at > now()", (_hash(code or ""),)).fetchone()
    if row is None:
        raise CodedError("bad_invite", "This invitation is expired or wrong; ask your teacher for a new one")
    return row


def peek_invite(code: str) -> dict:
    """Whose class an invitation is for."""
    with db.pool().connection() as conn:
        t = _teacher_of(conn, code)
        joined = conn.execute("SELECT 1 FROM class_members WHERE teacher_id = %s AND student_id = %s",
                              (t["id"], _me())).fetchone()
    return dict(teacher=t["email"], yours=t["id"] == _me(), joined=bool(joined))


def join(code: str) -> dict:
    with db.pool().connection() as conn:
        t = _teacher_of(conn, code)
        if t["id"] == _me():
            raise CodedError("own_class", "That's your own class")
        conn.execute("INSERT INTO class_members (teacher_id, student_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (t["id"], _me()))
    return dict(teacher=t["email"])


def leave(teacher_id: str) -> None:
    """A student leaves a class."""
    with db.pool().connection() as conn:
        conn.execute("DELETE FROM class_members WHERE teacher_id = %s AND student_id = %s", (teacher_id, _me()))


def remove(student_id: str) -> None:
    """A teacher removes a student."""
    with db.pool().connection() as conn:
        conn.execute("DELETE FROM class_members WHERE teacher_id = %s AND student_id = %s", (_me(), student_id))


def _student(conn, student_id: str) -> dict:
    row = conn.execute("SELECT u.id::text AS id, u.email FROM class_members m JOIN users u ON u.id = m.student_id "
                       "WHERE m.teacher_id = %s AND m.student_id = %s", (_me(), student_id)).fetchone()
    if row is None:
        raise CodedError("not_your_student", "That person isn't in your class")
    return row


def student_report(student_id: str) -> dict:
    """A student's weekly report, for their teacher."""
    with db.pool().connection() as conn:
        s = _student(conn, student_id)
    with config.use_user(s["id"]):
        r = report.week()
    return dict(r, student=s["email"])


def _summary(r: dict) -> dict:
    return dict(minutes=r["minutes"], active_days=r["active_days"], streak=r["streak"], xp=r["xp"],
                level=r["level"], songs=len(r["songs"]))


def overview() -> dict:
    """Your class (as a teacher) and your teachers (as a student), with what's waiting for you."""
    me = _me()
    with db.pool().connection() as conn:
        students = conn.execute(
            "SELECT u.id::text AS id, u.email, m.joined_at FROM class_members m JOIN users u ON u.id = m.student_id "
            "WHERE m.teacher_id = %s ORDER BY lower(u.email)", (me,)).fetchall()
        teachers = conn.execute(
            "SELECT u.id::text AS id, u.email, m.joined_at FROM class_members m JOIN users u ON u.id = m.teacher_id "
            "WHERE m.student_id = %s ORDER BY lower(u.email)", (me,)).fetchall()
        inbox = conn.execute(
            "SELECT a.id, u.email AS teacher, a.payload, a.created_at FROM assignments a JOIN users u ON u.id = a.teacher_id "
            "WHERE a.student_id = %s AND a.answered_at IS NULL ORDER BY a.id", (me,)).fetchall()
        sent = conn.execute(
            "SELECT id, student_id::text AS student_id, payload->>'name' AS name, created_at, answered_at, accepted "
            "FROM assignments WHERE teacher_id = %s ORDER BY id DESC LIMIT 100", (me,)).fetchall()
    out_students = []
    for s in students:
        with config.use_user(s["id"]):
            summary = _summary(report.week())
        out_students.append(dict(id=s["id"], email=s["email"], joined_at=s["joined_at"].isoformat(), week=summary,
                                 sent=[dict(id=a["id"], name=a["name"], created_at=a["created_at"].isoformat(),
                                            state="pending" if a["answered_at"] is None
                                            else "accepted" if a["accepted"] else "dismissed")
                                       for a in sent if a["student_id"] == s["id"]][:5]))
    return dict(
        students=out_students,
        teachers=[dict(id=t["id"], email=t["email"], joined_at=t["joined_at"].isoformat()) for t in teachers],
        inbox=[dict(id=a["id"], teacher=a["teacher"], name=a["payload"].get("name"), note=a["payload"].get("note"),
                    items=len(a["payload"].get("items", [])), created_at=a["created_at"].isoformat()) for a in inbox])


def send(student_id: str, setlist_id: str, note: str = "") -> dict:
    """Sends one of your setlists to a student of yours, with a note."""
    from psycopg.types.json import Jsonb
    from .setlists import SetlistError
    try:
        payload = assignment.export(setlist_id, str(note or "")[:MAX_NOTE])
    except (SetlistError, KeyError) as e:
        raise CodedError("setlist_not_found", "That setlist doesn't exist") from e
    with db.pool().connection() as conn:
        _student(conn, student_id)
        row = conn.execute("INSERT INTO assignments (teacher_id, student_id, payload) VALUES (%s, %s, %s) RETURNING id",
                           (_me(), student_id, Jsonb(payload))).fetchone()
    return dict(id=row["id"], name=payload["name"])


def answer(assignment_id: int, accept: bool) -> dict:
    """A student takes an assignment (a new setlist, with the teacher's charts) or dismisses it."""
    with db.pool().connection() as conn:
        row = conn.execute("SELECT a.payload FROM assignments a JOIN class_members m "
                           "ON m.teacher_id = a.teacher_id AND m.student_id = a.student_id "
                           "WHERE a.id = %s AND a.student_id = %s AND a.answered_at IS NULL",
                           (assignment_id, _me())).fetchone()
        if row is None:
            raise CodedError("no_assignment", "That assignment isn't waiting for you")
        result = None
        if accept:
            try:
                result = assignment.import_(row["payload"])
            except assignment.AssignmentError as e:
                raise CodedError("not_assignment", str(e)) from e
        conn.execute("UPDATE assignments SET answered_at = now(), accepted = %s WHERE id = %s", (accept, assignment_id))
    return dict(accepted=accept, setlist=result and result["setlist"], missing_songs=result and result["missing_songs"])
