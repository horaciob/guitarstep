"""Accounts for the web service: sign in with a one-time link sent by email, stay signed in with a cookie.

Only SHA-256 hashes of the link and cookie tokens are stored, so a copy of the database can't be
used to sign in. Without SMTP settings (local Docker Compose) the link is printed to the server
log instead of being emailed: `docker compose logs guitarr`.

    GUITARR_SMTP_HOST, GUITARR_SMTP_PORT (587), GUITARR_SMTP_USER, GUITARR_SMTP_PASSWORD,
    GUITARR_MAIL_FROM, GUITARR_PUBLIC_URL (the address in the link, e.g. https://guitarr.example)
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import smtplib
from email.message import EmailMessage

from . import db
from .errors import CodedError

LINK_MINUTES = 15
SESSION_DAYS = 30
LINKS_PER_HOUR = 5                 # per email address
COOKIE = "guitarr_session"
BROWSER_COOKIE = "guitarr_login"   # marks the browser that asked for a link
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email) -> str:
    e = str(email or "").strip()
    if len(e) > 254 or not EMAIL.match(e):
        raise CodedError("bad_email", "That doesn't look like an email address")
    return e


def request_link(email, base_url: str, send=None, browser: str | None = None) -> None:
    """Sends a sign-in link (a new account is made when it's first used). `browser` is the
    BROWSER_COOKIE of the browser that asked, to tell later whether the link is opened there."""
    email = normalize_email(email)
    token = secrets.token_urlsafe(32)
    with db.pool().connection() as conn:
        n = conn.execute("SELECT count(*) AS n FROM login_tokens WHERE lower(email) = lower(%s) "
                         "AND created_at > now() - interval '1 hour'", (email,)).fetchone()["n"]
        if n >= LINKS_PER_HOUR:
            raise CodedError("too_many_links", "Too many sign-in links for this address; try again in an hour")
        conn.execute("INSERT INTO login_tokens (token_hash, email, expires_at, browser_hash) "
                     "VALUES (%s, %s, now() + make_interval(mins => %s), %s)",
                     (_hash(token), email, LINK_MINUTES, browser and _hash(browser)))
    url = f"{(os.environ.get('GUITARR_PUBLIC_URL') or base_url).rstrip('/')}/auth/verify?token={token}"
    (send or send_link)(email, url)


def send_link(email: str, url: str) -> None:
    host = os.environ.get("GUITARR_SMTP_HOST")
    if not host:
        print(f"[guitarr] sign-in link for {email}: {url}", flush=True)
        return
    msg = EmailMessage()
    msg["Subject"] = "Your guitarr sign-in link"
    msg["From"] = os.environ.get("GUITARR_MAIL_FROM", "guitarr <no-reply@localhost>")
    msg["To"] = email
    msg.set_content(f"Open this link to sign in to guitarr (it works once, for {LINK_MINUTES} minutes):\n\n{url}\n\n"
                    "If you didn't ask for it, ignore this email.")
    with smtplib.SMTP(host, int(os.environ.get("GUITARR_SMTP_PORT", "587")), timeout=15) as s:
        s.starttls()
        if os.environ.get("GUITARR_SMTP_USER"):
            s.login(os.environ["GUITARR_SMTP_USER"], os.environ.get("GUITARR_SMTP_PASSWORD", ""))
        s.send_message(msg)


def peek_link(token: str, browser: str | None = None) -> dict:
    """Whose link this is, without using it: opening a link only shows "sign in as …" (so a link
    someone else sent you, or a mail scanner opening it, doesn't sign anybody in)."""
    with db.pool().connection() as conn:
        row = conn.execute("SELECT email, browser_hash FROM login_tokens WHERE token_hash = %s AND used_at IS NULL "
                           "AND expires_at > now()", (_hash(token or ""),)).fetchone()
    if row is None:
        raise CodedError("bad_link", "This sign-in link is used or expired; ask for a new one")
    return dict(email=row["email"], same_browser=bool(browser and row["browser_hash"] == _hash(browser)))


def redeem_link(token: str) -> tuple[str, dict]:
    """A link token → (session token for the cookie, user). The link works once."""
    with db.pool().connection() as conn:
        row = conn.execute("UPDATE login_tokens SET used_at = now() WHERE token_hash = %s AND used_at IS NULL "
                           "AND expires_at > now() RETURNING email", (_hash(token or ""),)).fetchone()
        if row is None:
            raise CodedError("bad_link", "This sign-in link is used or expired; ask for a new one")
        user = conn.execute(
            "INSERT INTO users (email, last_login) VALUES (%s, now()) "
            "ON CONFLICT ((lower(email))) DO UPDATE SET last_login = now() RETURNING id::text AS id, email, blocked_at",
            (row["email"],)).fetchone()
        if user.pop("blocked_at") is not None:
            raise CodedError("blocked", "This account is blocked")
        session = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) "
                     "VALUES (%s, %s, now() + make_interval(days => %s))", (_hash(session), user["id"], SESSION_DAYS))
    return session, user


def user_for(session: str | None) -> dict | None:
    """The signed-in user of a cookie, or None."""
    if not session:
        return None
    with db.pool().connection() as conn:
        return conn.execute(
            "UPDATE sessions s SET last_seen = now() FROM users u WHERE s.token_hash = %s AND s.expires_at > now() "
            "AND u.id = s.user_id AND u.blocked_at IS NULL RETURNING u.id::text AS id, u.email", (_hash(session),)).fetchone()


def sign_out(session: str | None) -> None:
    if session:
        with db.pool().connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash(session),))
