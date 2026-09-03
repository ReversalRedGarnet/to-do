"""services/task_service.py — in particular, the due-date normalization
that clamps any past due date forward to today (spec: applies to every
task-creation path, not just the quick-entry shorthand), and its
interaction with core/state_engine.py's color derivation."""

from datetime import date, timedelta

import pytest

from app.core.state_engine import Color, derive_color
from app.database.db import get_connection, initialize_database
from app.database.repositories.task_repository import TaskRepository
from app.notifications.notification_service import NullNotificationService
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
def task_service(conn):
    return TaskService(TaskRepository(conn), NullNotificationService())


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    from app.core import date_service
    monkeypatch.setattr(date_service, "today", lambda: TODAY)


def test_create_task_with_past_due_date_is_normalized_to_today(task_service):
    task = task_service.create_task("renew passport", due_date=TODAY - timedelta(days=3))
    assert task.due_date == TODAY


def test_create_task_with_future_due_date_is_unchanged(task_service):
    future = TODAY + timedelta(days=5)
    task = task_service.create_task("plan trip", due_date=future)
    assert task.due_date == future


def test_create_task_with_no_due_date_stays_none(task_service):
    task = task_service.create_task("someday maybe")
    assert task.due_date is None


def test_update_task_with_past_due_date_is_normalized_to_today(task_service):
    task = task_service.create_task("submit assignment")
    updated = task_service.update_task(task.id, due_date=TODAY - timedelta(days=1))
    assert updated.due_date == TODAY


def test_task_normalized_to_due_today_gets_yellow_color(task_service):
    """A task normalized to due_date == today must land in state_engine's
    existing "required attention today" bucket — verified against the
    real color rule rather than assumed."""
    task = task_service.create_task("renew passport", due_date=TODAY - timedelta(days=10))
    assert task.due_date == TODAY
    assert derive_color(task, TODAY, {"expected_date": None}) == Color.YELLOW
