"""Unit tests for services.recurrence_service and its wiring into
TaskService.complete_task — in particular, confirms the just-completed
recurring task's row is left intact (still COMPLETED, same id) and the
next occurrence is a brand new row, never an overwrite."""

from datetime import date, timedelta

import pytest

from app.database.db import get_connection, initialize_database
from app.database.repositories.recurrence_repository import RecurrenceRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.recurrence import RecurrenceFrequency
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.recurrence_service import RecurrenceService
from app.services.task_service import TaskService

TODAY = date(2026, 6, 15)


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
    recurrence_repo = RecurrenceRepository(conn)
    recurrence_service = RecurrenceService(task_repo, recurrence_repo)
    task_service = TaskService(task_repo, NullNotificationService(), recurrence_service)
    return dict(task_repo=task_repo, recurrence_repo=recurrence_repo,
                recurrence_service=recurrence_service, task_service=task_service)


def make_recurring_task(**overrides):
    defaults = dict(
        id=None, title="Weekly groceries", description="", task_type=TaskType.RECURRING,
        project_id=None, category="Personal", importance=2, urgency=2, seriousness=2,
        effort=1, available_from=TODAY, due_date=TODAY + timedelta(days=2),
        status=TaskStatus.SCHEDULED, created_at=TODAY,
    )
    defaults.update(overrides)
    return Task(**defaults)


def test_completing_a_non_recurring_task_spawns_nothing(wiring):
    task_id = wiring["task_repo"].create(make_recurring_task(recurrence_rule_id=None))
    wiring["task_service"].complete_task(task_id, completed_on=TODAY)

    all_tasks = wiring["task_repo"].list_all()
    assert len(all_tasks) == 1  # no next occurrence spawned


def test_completing_a_recurring_task_keeps_original_row_intact_and_spawns_next(wiring):
    task_id = wiring["task_repo"].create(make_recurring_task())
    wiring["recurrence_service"].set_recurrence(task_id, RecurrenceFrequency.WEEKLY)

    wiring["task_service"].complete_task(task_id, completed_on=TODAY)

    original = wiring["task_repo"].get_by_id(task_id)
    assert original.status == TaskStatus.COMPLETED
    assert original.completed_at == TODAY
    assert original.title == "Weekly groceries"  # untouched

    all_tasks = wiring["task_repo"].list_all()
    assert len(all_tasks) == 2  # original + new occurrence, never overwritten

    next_occurrence = next(t for t in all_tasks if t.id != task_id)
    assert next_occurrence.status == TaskStatus.PENDING
    assert next_occurrence.id != task_id
    assert next_occurrence.available_from == TODAY + timedelta(days=7)
    assert next_occurrence.due_date == TODAY + timedelta(days=9)  # window shape preserved
    assert next_occurrence.recurrence_rule_id == original.recurrence_rule_id


def test_daily_recurrence_shifts_by_one_day(wiring):
    task_id = wiring["task_repo"].create(
        make_recurring_task(available_from=TODAY, due_date=None)
    )
    wiring["recurrence_service"].set_recurrence(task_id, RecurrenceFrequency.DAILY)

    wiring["task_service"].complete_task(task_id, completed_on=TODAY)

    next_occurrence = next(t for t in wiring["task_repo"].list_all() if t.id != task_id)
    assert next_occurrence.available_from == TODAY + timedelta(days=1)
    assert next_occurrence.due_date is None


def test_clear_recurrence_stops_future_spawning(wiring):
    task_id = wiring["task_repo"].create(make_recurring_task())
    wiring["recurrence_service"].set_recurrence(task_id, RecurrenceFrequency.WEEKLY)
    wiring["recurrence_service"].clear_recurrence(task_id)

    wiring["task_service"].complete_task(task_id, completed_on=TODAY)

    assert len(wiring["task_repo"].list_all()) == 1
