"""
Notification abstraction. Isolate platform-specific (Windows toast) code
behind this interface so nothing else in the app imports a notification
library directly. Mock this class entirely in tests — never fire real
OS notifications from the test suite.
"""

from abc import ABC, abstractmethod


class NotificationService(ABC):
    @abstractmethod
    def notify_task(self, task) -> None:
        ...

    @abstractmethod
    def notify_event(self, event) -> None:
        ...

    @abstractmethod
    def notify_weekly_plan_required(self) -> None:
        ...

    @abstractmethod
    def notify_day_rollover(self, summary) -> None:
        ...


class WindowsNotificationService(NotificationService):
    """
    Concrete implementation. Prototype the underlying library (winotify or
    win11toast — not the unmaintained win10toast) in a standalone spike
    from a PyInstaller-frozen exe BEFORE building this out for real.
    """

    def notify_task(self, task) -> None:
        raise NotImplementedError

    def notify_event(self, event) -> None:
        raise NotImplementedError

    def notify_weekly_plan_required(self) -> None:
        raise NotImplementedError

    def notify_day_rollover(self, summary) -> None:
        raise NotImplementedError


class NullNotificationService(NotificationService):
    """No-op implementation for tests and headless runs."""

    def notify_task(self, task) -> None:
        pass

    def notify_event(self, event) -> None:
        pass

    def notify_weekly_plan_required(self) -> None:
        pass

    def notify_day_rollover(self, summary) -> None:
        pass
