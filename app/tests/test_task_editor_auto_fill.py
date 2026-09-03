"""Live smart auto-fill wiring inside TaskEditorDialog: the debounced
title-driven parse (core/title_parser.py), the "stop overwriting after a
manual edit" guardrail, and the visual auto-filled marker. Most tests
call `dialog._apply_title_hints()` directly after setting the title text
— the same technique the rest of the suite uses to drive a handler
without waiting on real Qt timing (see e.g. test_task_editing.py) — with
one end-to-end test that lets the real debounce timer fire."""

from datetime import date

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.task_service import TaskService
from app.ui.task_editor import _AUTO_FILL_STYLE, TaskEditorDialog

MONDAY = date(2026, 6, 15)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    """_apply_title_hints reads app.core.date_service.today() for "now" —
    pin it to MONDAY so the deadline-convention assertions below are
    exact regardless of what day the suite actually runs on."""
    from app.core import date_service
    monkeypatch.setattr(date_service, "today", lambda: MONDAY)


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
    category_repo = CategoryRepository(conn)
    project_repo = ProjectRepository(conn)
    task_service = TaskService(task_repo, NullNotificationService())
    return dict(task_repo=task_repo, category_repo=category_repo, project_repo=project_repo,
                task_service=task_service)


def make_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Original title", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=2, due_date=None,
        status=TaskStatus.PENDING, created_at=MONDAY,
    )
    defaults.update(overrides)
    task_id = wiring["task_repo"].create(Task(**defaults))
    return wiring["task_repo"].get_by_id(task_id)


def make_dialog(wiring, task, *, with_projects=False):
    project_repo = wiring["project_repo"] if with_projects else None
    return TaskEditorDialog(task, wiring["category_repo"].list_all(), wiring["task_service"],
                             project_repository=project_repo)


def retype(dialog, text: str) -> None:
    """Sets the title text and runs the parse immediately, bypassing the
    real 400ms debounce timer (see test_debounce_actually_fires_after_a_
    pause below for a test of the timer itself)."""
    dialog._title.setText(text)
    dialog._apply_title_hints()


# --- Each trigger category ---

def test_typing_a_weekday_auto_fills_the_due_date(wiring):
    task = make_task(wiring)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Team sync sat")

    assert dialog._due_date_enabled.isChecked() is True
    assert dialog._due_date.date().toPython() == date(2026, 6, 19)  # Friday, day before Sat


def test_typing_quick_auto_fills_low_effort(wiring):
    task = make_task(wiring, effort=3)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Quick errand")

    assert dialog._effort.value() == 1


def test_typing_huge_auto_fills_high_effort(wiring):
    task = make_task(wiring, effort=3)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Huge migration project")

    assert dialog._effort.value() == 5


def test_typing_urgent_bumps_urgency(wiring):
    task = make_task(wiring, urgency=2)
    dialog = make_dialog(wiring, task)

    retype(dialog, "urgent server issue")

    assert dialog._urgency.value() == 5


def test_typing_important_bumps_importance(wiring):
    task = make_task(wiring, importance=2)
    dialog = make_dialog(wiring, task)

    retype(dialog, "important review")

    assert dialog._importance.value() == 5


def test_typing_a_project_name_auto_selects_it(wiring):
    project_id = wiring["project_repo"].create(Project(id=None, name="Launch", description=""))
    task = make_task(wiring)
    dialog = make_dialog(wiring, task, with_projects=True)

    retype(dialog, "Fix launch page bug")

    assert dialog._project.currentData() == project_id


# --- Deadline day-before convention, at the dialog level ---

def test_tomorrow_sets_deadline_to_today_at_the_dialog_level(wiring):
    task = make_task(wiring)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Call mom tomorrow")

    assert dialog._due_date.date().toPython() == MONDAY


def test_today_never_triggers_a_deadline_auto_fill(wiring):
    task = make_task(wiring)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Finish this today")

    assert dialog._due_date_enabled.isChecked() is False


# --- Guardrail: stop overwriting a field once the user manually edits it ---

def test_manually_edited_due_date_is_never_overwritten_by_a_later_title_change(wiring):
    task = make_task(wiring)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Team sync sat")
    assert dialog._due_date.date().toPython() == date(2026, 6, 19)

    dialog._due_date.setDate(dialog._due_date.date().addDays(3))  # user manually moves it
    manually_set = dialog._due_date.date().toPython()

    retype(dialog, "Team sync next sun")  # a completely different day mention

    assert dialog._due_date.date().toPython() == manually_set


def test_manually_edited_effort_is_never_overwritten_by_a_later_title_change(wiring):
    task = make_task(wiring, effort=3)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Quick task")
    assert dialog._effort.value() == 1

    dialog._effort.setValue(4)  # user overrides the inferred value
    retype(dialog, "Huge task")  # would otherwise push it to 5

    assert dialog._effort.value() == 4


def test_only_the_manually_edited_field_stops_updating_others_still_auto_fill(wiring):
    task = make_task(wiring, effort=3, urgency=2)
    dialog = make_dialog(wiring, task)

    retype(dialog, "urgent quick task")
    dialog._effort.setValue(2)  # manually override effort only

    retype(dialog, "urgent huge task")  # urgency hint repeats, effort hint changes

    assert dialog._effort.value() == 2  # untouched — manual edit protected it
    assert dialog._urgency.value() == 5  # still auto-fillable


def test_title_text_itself_is_never_modified_by_auto_fill(wiring):
    task = make_task(wiring)
    dialog = make_dialog(wiring, task)

    retype(dialog, "  Quick urgent sat call  ")

    assert dialog._title.text() == "  Quick urgent sat call  "


# --- Visual marker state ---

def test_auto_filled_field_gets_the_marker_style(wiring):
    task = make_task(wiring, effort=3)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Quick task")

    assert dialog._auto_filled["effort"] is True
    assert dialog._effort.styleSheet() == _AUTO_FILL_STYLE


def test_a_field_never_touched_by_a_hint_has_no_marker(wiring):
    task = make_task(wiring)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Quick task")  # no urgency/importance hint here

    assert dialog._auto_filled["urgency"] is False
    assert dialog._urgency.styleSheet() == ""


def test_marker_clears_once_the_user_manually_edits_that_field(wiring):
    task = make_task(wiring, effort=3)
    dialog = make_dialog(wiring, task)

    retype(dialog, "Quick task")
    assert dialog._auto_filled["effort"] is True

    dialog._effort.setValue(4)

    assert dialog._auto_filled["effort"] is False
    assert dialog._effort.styleSheet() == ""


# --- The real debounce timer ---

def test_debounce_actually_fires_after_a_pause(wiring):
    task = make_task(wiring, effort=3)
    dialog = make_dialog(wiring, task)

    dialog._title.setText("Quick task")
    assert dialog._effort.value() == 3  # not applied yet — debounce hasn't elapsed

    QTest.qWait(500)

    assert dialog._effort.value() == 1
