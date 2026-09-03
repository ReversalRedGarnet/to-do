"""Audit fix #1: TaskService.defer_task previously set TaskStatus.SCHEDULED
instead of TaskStatus.DEFERRED, leaving state_engine.derive_color's
DEFERRED guard, ProjectView's "Deferred" grouping, and TaskCard's
"Deferred" label all unreachable in production despite being fully
implemented and tested in isolation against a synthetic DEFERRED task
(see test_state_transitions.py). This exercises the real service call
end to end instead of constructing the status directly."""

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from app.core.state_engine import Color, derive_color
from app.database.db import get_connection, initialize_database
from app.database.repositories.task_repository import TaskRepository
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.task_service import TaskService
from app.ui.widgets.task_card import TaskCard

TODAY = date(2026, 6, 17)
TOMORROW = date(2026, 6, 18)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


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
    task_service = TaskService(task_repo, NullNotificationService())
    return dict(task_repo=task_repo, task_service=task_service)


def make_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Task due today", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=TODAY,
        status=TaskStatus.SCHEDULED, created_at=TODAY, current_scheduled_date=TODAY,
    )
    defaults.update(overrides)
    task_id = wiring["task_repo"].create(Task(**defaults))
    return wiring["task_repo"].get_by_id(task_id)


def test_defer_task_sets_status_to_deferred(wiring):
    task = make_task(wiring)

    deferred = wiring["task_service"].defer_task(task.id, TOMORROW, today=TODAY)

    assert deferred.status == TaskStatus.DEFERRED
    persisted = wiring["task_repo"].get_by_id(task.id)
    assert persisted.status == TaskStatus.DEFERRED


def test_deferring_a_task_due_today_no_longer_renders_yellow(wiring):
    """Before the fix, defer_task left status=SCHEDULED, so derive_color's
    `today == task.due_date` fallback still painted a just-deferred task
    yellow — indistinguishable from "needs attention today"."""
    task = make_task(wiring, due_date=TODAY)

    deferred = wiring["task_service"].defer_task(task.id, TOMORROW, today=TODAY)

    context = {"expected_date": deferred.current_scheduled_date}
    assert derive_color(deferred, TODAY, context) != Color.YELLOW
    assert derive_color(deferred, TODAY, context) is None


def test_deferred_task_card_shows_the_deferred_label(wiring):
    task = make_task(wiring, due_date=TODAY)
    deferred = wiring["task_service"].defer_task(task.id, TOMORROW, today=TODAY)

    card = TaskCard(deferred, None, today=TODAY)

    meta_text = " ".join(label.text() for label in card.findChildren(QLabel))
    assert "Deferred" in meta_text
    assert "Scheduled" not in meta_text
