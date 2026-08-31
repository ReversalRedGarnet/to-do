"""Verifies the TaskEditorDialog "Repeats" control itself (spec: recurrence
must be usable through the app, not just RecurrenceService directly) —
constructs the real dialog widget and exercises its save path without
showing/exec()ing it (QDialog works fine headless as long as a
QApplication instance exists)."""

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.recurrence_repository import RecurrenceRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.recurrence import RecurrenceFrequency
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.recurrence_service import RecurrenceService
from app.services.task_service import TaskService
from app.ui.task_editor import TaskEditorDialog

TODAY = date(2026, 6, 15)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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
    category_repo = CategoryRepository(conn)
    recurrence_service = RecurrenceService(task_repo, recurrence_repo)
    task_service = TaskService(task_repo, NullNotificationService(), recurrence_service)
    return dict(task_repo=task_repo, recurrence_service=recurrence_service,
                task_service=task_service, categories=category_repo.list_all())


def make_task(task_repo, **overrides):
    defaults = dict(
        id=None, title="Weekly groceries", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=2, urgency=2, seriousness=2,
        effort=1, available_from=TODAY, due_date=None,
        status=TaskStatus.PENDING, created_at=TODAY,
    )
    defaults.update(overrides)
    task_id = task_repo.create(Task(**defaults))
    return task_repo.get_by_id(task_id)


def test_setting_weekly_recurrence_through_the_dialog_persists_it(wiring):
    task = make_task(wiring["task_repo"])
    dialog = TaskEditorDialog(
        task, wiring["categories"], wiring["task_service"],
        recurrence_service=wiring["recurrence_service"],
    )

    weekly_index = dialog._frequency.findData(RecurrenceFrequency.WEEKLY)
    dialog._frequency.setCurrentIndex(weekly_index)
    dialog._interval.setValue(2)

    dialog._save()

    rule = wiring["recurrence_service"].get_rule_for_task(wiring["task_repo"].get_by_id(task.id))
    assert rule.frequency == RecurrenceFrequency.WEEKLY
    assert rule.interval == 2


def test_setting_custom_weekdays_through_the_dialog_persists_selected_days(wiring):
    task = make_task(wiring["task_repo"])
    dialog = TaskEditorDialog(
        task, wiring["categories"], wiring["task_service"],
        recurrence_service=wiring["recurrence_service"],
    )

    custom_index = dialog._frequency.findData(RecurrenceFrequency.CUSTOM_WEEKDAYS)
    dialog._frequency.setCurrentIndex(custom_index)
    dialog._weekday_boxes[0].setChecked(True)  # Monday
    dialog._weekday_boxes[4].setChecked(True)  # Friday

    dialog._save()

    rule = wiring["recurrence_service"].get_rule_for_task(wiring["task_repo"].get_by_id(task.id))
    assert rule.frequency == RecurrenceFrequency.CUSTOM_WEEKDAYS
    assert sorted(rule.weekdays) == [0, 4]


def test_reopening_dialog_prefills_existing_recurrence(wiring):
    task = make_task(wiring["task_repo"])
    wiring["recurrence_service"].set_recurrence(task.id, RecurrenceFrequency.MONTHLY, interval=3)

    reloaded_task = wiring["task_repo"].get_by_id(task.id)
    dialog = TaskEditorDialog(
        reloaded_task, wiring["categories"], wiring["task_service"],
        recurrence_service=wiring["recurrence_service"],
    )

    assert dialog._frequency.currentData() == RecurrenceFrequency.MONTHLY
    assert dialog._interval.value() == 3


def test_setting_frequency_back_to_none_clears_recurrence(wiring):
    task = make_task(wiring["task_repo"])
    wiring["recurrence_service"].set_recurrence(task.id, RecurrenceFrequency.DAILY)
    reloaded_task = wiring["task_repo"].get_by_id(task.id)

    dialog = TaskEditorDialog(
        reloaded_task, wiring["categories"], wiring["task_service"],
        recurrence_service=wiring["recurrence_service"],
    )
    none_index = dialog._frequency.findData(None)
    dialog._frequency.setCurrentIndex(none_index)
    dialog._save()

    final_task = wiring["task_repo"].get_by_id(task.id)
    assert final_task.recurrence_rule_id is None


def test_completing_task_edited_to_recurring_spawns_next_occurrence(wiring):
    task = make_task(wiring["task_repo"], due_date=TODAY)
    dialog = TaskEditorDialog(
        task, wiring["categories"], wiring["task_service"],
        recurrence_service=wiring["recurrence_service"],
    )
    weekly_index = dialog._frequency.findData(RecurrenceFrequency.WEEKLY)
    dialog._frequency.setCurrentIndex(weekly_index)
    dialog._save()

    wiring["task_service"].complete_task(task.id, completed_on=TODAY)

    original = wiring["task_repo"].get_by_id(task.id)
    assert original.status == TaskStatus.COMPLETED

    all_tasks = wiring["task_repo"].list_all()
    assert len(all_tasks) == 2
