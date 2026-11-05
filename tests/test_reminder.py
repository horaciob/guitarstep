"""Daily reminder."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from guitarr import config, plan, reminder
from guitarr.gui.server import app


def at(h, m=0):
    d = datetime.now()
    return d.replace(hour=h, minute=m, second=0, microsecond=0)


def test_defaults_are_off():
    r = reminder.get()
    assert r["enabled"] is False and r["time"] == "19:00"
    assert reminder.due(at(23)) is None


def test_due_only_after_the_time_once_a_day_and_if_the_goal_is_not_met():
    reminder.update(True, "18:30", "guitarr", "Te faltan {left} hoy")
    assert reminder.due(at(18, 29)) is None
    assert reminder.due(at(18, 30)) == "Te faltan 0:30 hoy"
    reminder.mark_sent()
    assert reminder.due(at(21)) is None                       # already sent today
    c = config.load(); c["reminder"]["last_sent"] = ""; config.save(c)
    plan.record_session(dict(type="practice"), dict(summary=dict(played_s=31 * 60)))
    assert reminder.due(at(21)) is None                       # goal met


def test_settings_survive_other_config_changes():
    reminder.update(True, "07:05")
    config.update_audio(latency_ms=12.0)
    assert reminder.get()["time"] == "07:05" and config.load()["audio"]["latency_ms"] == 12.0


@pytest.mark.parametrize("bad", ["25:00", "7:5", "abc", ""])
def test_bad_time_is_rejected(bad):
    with pytest.raises(reminder.ReminderError):
        reminder.update(time=bad)


def test_check_once_sends_with_a_desktop_notifier(monkeypatch):
    sent = []
    monkeypatch.setattr(reminder, "notifier", lambda: ["notify-send"])
    monkeypatch.setattr(reminder, "notify", lambda t, b: sent.append((t, b)) or True)
    reminder.update(True, "06:00", "guitarr", "{left} left")
    assert reminder.check_once(at(6, 1)) and sent == [("guitarr", "0:30 left")]
    assert not reminder.check_once(at(6, 2))                  # once a day


def test_reminder_api(monkeypatch):
    monkeypatch.setattr(reminder, "notifier", lambda: None)
    c = TestClient(app)
    r = c.put("/api/reminder", json=dict(enabled=True, time="00:00", body="{left} to go")).json()
    assert r["enabled"] and r["desktop"] is False
    assert c.get("/api/reminder").json()["due"] == "0:30 to go"
    c.post("/api/reminder/shown")
    assert c.get("/api/reminder").json()["due"] is None
    assert c.put("/api/reminder", json=dict(time="99:99")).json()["detail"]["code"] == "bad_time"
