"""Unit tests for main._send_startup_notifications — the decision logic for
which of the four notification types fire at app launch (spec §31), using a
spy NotificationService rather than any real OS toast."""

from datetime import date, timedelta

import pytest

from app.core.state_engine import ReconciliationResult
from app.database.db import get_connection, initialize_database
from app.database.repositories.app_state_repository import AppStateRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.settings_repository import SettingsRepository
from app.database.repositories.task_repository import TaskRepository
from app.main import _send_startup_notifications
from app.models.fixed_event import FixedEvent
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NotificationService
from app.services.schedule_service import ScheduleService

# A Monday so weekday() < _PLANNING_REMINDER_WEEKDAY (Sunday=6) in most tests.
MONDAY = date(2026, 6, 15)
SUNDAY = MONDAY + timedelta(days=6)


class SpyNotificationService(NotificationService):
    def __init__(self):
        self.tasks = []
        self.events = []
        self.weekly_plan_required_calls = 0
        self.rollover_calls = []
        self.missed_batches = []

    def notify_task(self, task, *, missed: bool = False) -> None:
        self.tasks.append((task, missed))

    def notify_event(self, event) -> None:
        self.events.append(event)

    def notify_weekly_plan_required(self) -> None:
        self.weekly_plan_required_calls += 1

    def notify_day_rollover(self, summary: dict) -> None:
        self.rollover_calls.append(summary)

    def notify_missed_tasks(self, missed_tasks: list) -> None:
        self.missed_batches.append(missed_tasks)


def make_task(**overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=MONDAY, due_date=None,
        status=TaskStatus.SCHEDULED, created_at=MONDAY,
    )
    defaults.update(overrides)
    return Task(**defaults)


def empty_result(missed_ids=None):
    return ReconciliationResult(
        reconciled_dates=[], tasks_marked_missed=missed_ids or [],
        state_transitions=[], weeks_archived=[], new_today_board=[],
    )


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def wiring(conn):
    task_repo = TaskRepository(conn)
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)
    app_state_repo = AppStateRepository(conn)
    settings_repo = SettingsRepository(conn)
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    spy = SpyNotificationService()
    return dict(
        task_repo=task_repo, schedule_repo=schedule_repo, fixed_event_repo=fixed_event_repo,
        app_state_repo=app_state_repo, settings_repo=settings_repo,
        schedule_service=schedule_service, spy=spy,
    )


def test_missed_tasks_trigger_one_summary_batch(wiring):
    task_id = wiring["task_repo"].create(make_task())
    result = empty_result(missed_ids=[task_id])

    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )

    assert len(wiring["spy"].missed_batches) == 1
    assert wiring["spy"].missed_batches[0][0].id == task_id


def test_no_missed_tasks_no_batch_sent(wiring):
    result = empty_result()
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )
    assert wiring["spy"].missed_batches == []


def test_weekly_plan_reminder_fires_on_sunday_when_next_week_unplanned(wiring):
    result = empty_result()
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, SUNDAY,
    )
    assert wiring["spy"].weekly_plan_required_calls == 1


def test_weekly_plan_reminder_does_not_fire_on_a_weekday(wiring):
    result = empty_result()
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )
    assert wiring["spy"].weekly_plan_required_calls == 0


def test_weekly_plan_reminder_suppressed_when_setting_disabled(wiring, conn):
    settings = wiring["settings_repo"].get()
    settings.sunday_reminder_enabled = False
    wiring["settings_repo"].update(settings)

    result = empty_result()
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, SUNDAY,
    )
    assert wiring["spy"].weekly_plan_required_calls == 0


def test_fixed_event_today_triggers_notify_event(wiring):
    wiring["fixed_event_repo"].create(
        FixedEvent(id=None, title="Tutoring", description="", event_date=MONDAY)
    )
    result = empty_result()
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )
    assert len(wiring["spy"].events) == 1
    assert wiring["spy"].events[0].title == "Tutoring"


def test_highest_priority_todays_task_gets_notified(wiring):
    low_id = wiring["task_repo"].create(make_task(importance=1, urgency=1, seriousness=1))
    high_id = wiring["task_repo"].create(make_task(importance=5, urgency=5, seriousness=5))
    wiring["schedule_repo"].replace_week(
        MONDAY,
        [
            ScheduleEntry(id=None, task_id=low_id, week_start=MONDAY,
                           scheduled_date=MONDAY, schedule_reason="TEST"),
            ScheduleEntry(id=None, task_id=high_id, week_start=MONDAY,
                           scheduled_date=MONDAY, schedule_reason="TEST"),
        ],
    )
    result = empty_result()
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )
    assert len(wiring["spy"].tasks) == 1
    notified_task, missed_flag = wiring["spy"].tasks[0]
    assert notified_task.id == high_id
    assert missed_flag is False


def test_already_notified_today_suppresses_everything(wiring):
    task_id = wiring["task_repo"].create(make_task())
    result = empty_result(missed_ids=[task_id])
    wiring["app_state_repo"].set_last_notified_date(MONDAY)

    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )

    assert wiring["spy"].missed_batches == []
    assert wiring["spy"].tasks == []
    assert wiring["spy"].events == []
    assert wiring["spy"].weekly_plan_required_calls == 0


def test_running_twice_only_notifies_once(wiring):
    task_id = wiring["task_repo"].create(make_task())
    result = empty_result(missed_ids=[task_id])

    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )

    assert len(wiring["spy"].missed_batches) == 1


def test_notify_day_rollover_never_fires_from_startup_path(wiring):
    """Reserved for the mid-session timer (ui/main_window.py) — see the
    approved Phase 7 plan."""
    task_id = wiring["task_repo"].create(make_task())
    result = empty_result(missed_ids=[task_id])
    _send_startup_notifications(
        wiring["spy"], wiring["task_repo"], wiring["schedule_service"],
        wiring["app_state_repo"], wiring["settings_repo"], result, MONDAY,
    )
    assert wiring["spy"].rollover_calls == []
