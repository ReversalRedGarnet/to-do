"""Unit tests for notifications.notification_service.

Never fires a real OS toast here — WindowsNotificationService is tested
against a monkeypatched winotify.Notification, and NullNotificationService
is tested for being a safe no-op. See spec §54 "Mock the notification
layer in tests."
"""

from dataclasses import dataclass

import pytest

from app.notifications.notification_service import (
    NullNotificationService,
    WindowsNotificationService,
)


@dataclass
class _FakeSettings:
    notifications_enabled: bool


class _FakeSettingsRepository:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def get(self):
        return _FakeSettings(notifications_enabled=self._enabled)


class _RecordingNotification:
    """Stand-in for winotify.Notification — records construction args and
    show() calls instead of touching the OS."""
    calls = []

    def __init__(self, app_id, title, msg, duration="short"):
        self.app_id = app_id
        self.title = title
        self.msg = msg

    def show(self):
        _RecordingNotification.calls.append((self.title, self.msg))


@pytest.fixture(autouse=True)
def _reset_recorder():
    _RecordingNotification.calls = []
    yield


@pytest.fixture
def patched_winotify(monkeypatch):
    import winotify
    monkeypatch.setattr(winotify, "Notification", _RecordingNotification)
    return _RecordingNotification


class _Task:
    def __init__(self, title):
        self.title = title


class _Event:
    def __init__(self, title, event_time=None):
        self.title = title
        self.event_time = event_time


def test_disabled_settings_suppresses_all_notifications(patched_winotify):
    service = WindowsNotificationService(_FakeSettingsRepository(enabled=False))
    service.notify_task(_Task("Finish report"))
    service.notify_event(_Event("Tutoring"))
    service.notify_weekly_plan_required()
    service.notify_day_rollover({"priority_task_count": 1, "event_count": 0})
    service.notify_missed_tasks([_Task("A"), _Task("B")])

    assert patched_winotify.calls == []


def test_notify_task_upcoming_vs_missed_wording(patched_winotify):
    service = WindowsNotificationService(_FakeSettingsRepository(enabled=True))

    service.notify_task(_Task("Finish report"))
    title, msg = patched_winotify.calls[-1]
    assert "Finish report" in msg
    assert "didn't" not in msg.lower()

    service.notify_task(_Task("Finish report"), missed=True)
    title, msg = patched_winotify.calls[-1]
    assert "didn't complete" in msg.lower()
    assert "Finish report" in msg


def test_notify_event_includes_time_when_present(patched_winotify):
    service = WindowsNotificationService(_FakeSettingsRepository(enabled=True))
    service.notify_event(_Event("Tutoring", event_time="15:00"))
    _, msg = patched_winotify.calls[-1]
    assert "Tutoring" in msg and "15:00" in msg


def test_notify_missed_tasks_single_task_uses_missed_wording(patched_winotify):
    service = WindowsNotificationService(_FakeSettingsRepository(enabled=True))
    service.notify_missed_tasks([_Task("Only task")])
    assert len(patched_winotify.calls) == 1
    _, msg = patched_winotify.calls[0]
    assert "didn't complete" in msg.lower()


def test_notify_missed_tasks_multiple_sends_one_summary(patched_winotify):
    service = WindowsNotificationService(_FakeSettingsRepository(enabled=True))
    tasks = [_Task(f"Task {i}") for i in range(5)]
    service.notify_missed_tasks(tasks)

    assert len(patched_winotify.calls) == 1  # one summary, not five toasts
    title, msg = patched_winotify.calls[0]
    assert "5" in title
    assert "+2 more" in msg


def test_notify_missed_tasks_empty_list_sends_nothing(patched_winotify):
    service = WindowsNotificationService(_FakeSettingsRepository(enabled=True))
    service.notify_missed_tasks([])
    assert patched_winotify.calls == []


def test_broken_winotify_is_swallowed_not_raised(monkeypatch):
    import winotify

    def _boom(*args, **kwargs):
        raise RuntimeError("no toast backend available")

    monkeypatch.setattr(winotify, "Notification", _boom)
    service = WindowsNotificationService(_FakeSettingsRepository(enabled=True))
    service.notify_task(_Task("Should not crash"))  # must not raise


def test_null_notification_service_is_a_safe_noop():
    service = NullNotificationService()
    service.notify_task(_Task("x"))
    service.notify_event(_Event("y"))
    service.notify_weekly_plan_required()
    service.notify_day_rollover({})
    service.notify_missed_tasks([_Task("z")])
