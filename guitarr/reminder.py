"""Daily practice reminder: at the time you choose, if today's goal isn't met yet, a desktop
notification tells you how much is left.

Settings live in config.toml ([reminder]). The texts come from the UI in your language
(`title` and `body` with a {left} placeholder), so the server never has to translate.
Notifications use `osascript` on macOS and `notify-send` on Linux; when neither is
available (e.g. in Docker), the web page shows a browser notification instead.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from datetime import date, datetime

from . import config, plan

DEFAULTS = dict(enabled=False, time="19:00", title="guitarr", body="{left} left today to meet your goal",
                last_sent="")
_lock = threading.Lock()


class ReminderError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def get() -> dict:
    r = {**DEFAULTS, **config.load().get("reminder", {})}
    return {**r, "desktop": notifier() is not None}


def update(enabled=None, time=None, title=None, body=None) -> dict:
    with _lock:
        data = config.load()
        r = {**DEFAULTS, **data.get("reminder", {})}
        if time is not None:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(time)):
                raise ReminderError("bad_time", "Use a time like 19:30")
            r["time"] = str(time)
        if enabled is not None:
            r["enabled"] = bool(enabled)
        for k, v in (("title", title), ("body", body)):
            if v is not None:
                v = str(v).strip()[:200]
                if v:
                    r[k] = v
        data["reminder"] = r
        config.save(data)
    return get()


def notifier() -> list[str] | None:
    if sys.platform == "darwin" and shutil.which("osascript"):
        return ["osascript"]
    if shutil.which("notify-send"):
        return ["notify-send"]
    return None


def notify(title: str, body: str) -> bool:
    cmd = notifier()
    if not cmd:
        return False
    if cmd[0] == "osascript":
        q = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
        args = ["osascript", "-e", f'display notification "{q(body)}" with title "{q(title)}"']
    else:
        args = ["notify-send", "--app-name=guitarr", title, body]
    try:
        subprocess.run(args, check=False, timeout=10, capture_output=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def fmt_left(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def due(now: datetime | None = None, cfg: dict | None = None, today_view: dict | None = None) -> str | None:
    """The message to send now, or None (disabled, too early, already sent, or goal met)."""
    now = now or datetime.now()
    cfg = cfg or get()
    if not cfg["enabled"] or cfg.get("last_sent") == now.date().isoformat():
        return None
    if now.strftime("%H:%M") < cfg["time"]:
        return None
    td = today_view or plan.get()["today"]
    if td["remaining"] <= 0:
        return None
    return cfg["body"].replace("{left}", fmt_left(td["remaining"]))


def mark_sent(day: date | None = None) -> None:
    with _lock:
        data = config.load()
        r = {**DEFAULTS, **data.get("reminder", {})}
        r["last_sent"] = (day or date.today()).isoformat()
        data["reminder"] = r
        config.save(data)


def check_once(now: datetime | None = None) -> bool:
    cfg = get()
    msg = due(now, cfg)
    if msg and cfg["desktop"] and notify(cfg["title"], msg):
        mark_sent((now or datetime.now()).date())
        return True
    return False


def start_loop(every: float = 30.0) -> threading.Thread:
    """Checks every `every` seconds while the server runs."""
    stop = threading.Event()

    def run():
        while not stop.wait(every):
            try:
                check_once()
            except Exception:       # never take the server down for a reminder
                pass

    th = threading.Thread(target=run, daemon=True, name="guitarr-reminder")
    th.start()
    th.stop = stop.set
    return th
