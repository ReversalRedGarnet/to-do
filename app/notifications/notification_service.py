"""
Notification abstraction. Isolate platform-specific (Windows toast) code
behind this interface so nothing else in the app imports a notification
library directly. Mock this class entirely in tests — never fire real
OS notifications from the test suite.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class NotificationService(ABC):
    @abstractmethod
    def notify_task(self, task, *, missed: bool = False) -> None:
        """Single-task notification. `missed=True` reads as "You didn't
        complete: X" (spec §31 Missed task); otherwise "Today: X"
        (Upcoming daily task)."""
        ...

    @abstractmethod
    def notify_event(self, event) -> None:
        ...

    @abstractmethod
    def notify_weekly_plan_required(self) -> None:
        ...

    @abstractmethod
    def notify_day_rollover(self, summary: dict) -> None:
        ...

    @abstractmethod
    def notify_missed_tasks(self, missed_tasks: list) -> None:
        """Spec §33 lists notify_task/notify_event/notify_weekly_plan_required/
        notify_day_rollover as examples ("methods such as"), not an
        exhaustive interface — this covers the "several tasks missed after
        a gap" case, where firing one notify_task per task would be exactly
        the notification spam spec §31 warns against."""
        ...


class WindowsNotificationService(NotificationService):
    """
    Concrete implementation using winotify — chosen after the Phase 1
    go/no-go spike (scripts/notification_spike.py) confirmed it fires
    correctly from a PyInstaller-frozen exe, visually confirmed by the user.

    Every method is defensive: a broken toast (missing winotify install,
    an OS-level failure) is logged and swallowed, never allowed to crash
    the planner — notifications are a nicety, not a dependency the rest
    of the app can fail on.
    """

    def __init__(self, settings_repository, app_id: str = "TaskPlanner"):
        self._settings = settings_repository
        self._app_id = app_id

    def _enabled(self) -> bool:
        try:
            return self._settings.get().notifications_enabled
        except Exception:
            logger.exception("Could not read notification settings; suppressing notification")
            return False

    def _show(self, title: str, msg: str) -> None:
        if not self._enabled():
            return
        try:
            from winotify import Notification
            Notification(app_id=self._app_id, title=title, msg=msg, duration="short").show()
        except Exception:
            logger.exception("Failed to show notification: %s / %s", title, msg)

    def notify_task(self, task, *, missed: bool = False) -> None:
        if missed:
            self._show("Missed task", f"You didn't complete: {task.title}")
        else:
            self._show("Today", task.title)

    def notify_event(self, event) -> None:
        when = f" at {event.event_time}" if event.event_time else ""
        self._show("Scheduled event today", f"{event.title}{when}")

    def notify_weekly_plan_required(self) -> None:
        self._show("Planning needed", "Your week hasn't been planned yet.")

    def notify_day_rollover(self, summary: dict) -> None:
        task_count = summary.get("priority_task_count", 0)
        event_count = summary.get("event_count", 0)
        self._show(
            "Today has been updated",
            f"{task_count} priority task(s), {event_count} scheduled event(s).",
        )

    def notify_missed_tasks(self, missed_tasks: list) -> None:
        if not missed_tasks:
            return
        if len(missed_tasks) == 1:
            self.notify_task(missed_tasks[0], missed=True)
            return
        titles = ", ".join(t.title for t in missed_tasks[:3])
        more = f" (+{len(missed_tasks) - 3} more)" if len(missed_tasks) > 3 else ""
        self._show(
            f"{len(missed_tasks)} tasks missed",
            f"{titles}{more}",
        )


class NullNotificationService(NotificationService):
    """No-op implementation for tests and headless runs."""

    def notify_task(self, task, *, missed: bool = False) -> None:
        pass

    def notify_event(self, event) -> None:
        pass

    def notify_weekly_plan_required(self) -> None:
        pass

    def notify_day_rollover(self, summary: dict) -> None:
        pass

    def notify_missed_tasks(self, missed_tasks: list) -> None:
        pass
