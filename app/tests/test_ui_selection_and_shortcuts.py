"""Verifies the Phase 9 card-selection model and the panel-level methods
the keyboard shortcuts call into (spec §50). Modal dialogs
(TaskEditorDialog, WeeklyBoard's _DeferDialog) are monkeypatched to
auto-accept so tests don't block on a real event loop — the same
technique test_task_editor_recurrence.py uses to exercise the dialog
directly instead."""

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.core.date_service import week_start
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.schedule_service import ScheduleService
from app.services.task_service import TaskService
from app.ui.main_window import TodayPanel
from app.ui.weekly_board import WeeklyBoard
from app.ui.widgets.task_card import TaskCard


# TodayPanel/WeeklyBoard read the real wall-clock date directly
# (datetime.date.today()) rather than through core.date_service, so tests
# schedule against the actual current date rather than a fixed one.
TODAY = date.today()


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def auto_accept_dialogs(monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


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
    category_repo = CategoryRepository(conn)
    task_service = TaskService(task_repo, NullNotificationService())
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    return dict(task_repo=task_repo, schedule_repo=schedule_repo,
                category_repo=category_repo, task_service=task_service,
                schedule_service=schedule_service)


def make_scheduled_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=TODAY, due_date=None,
        status=TaskStatus.SCHEDULED, created_at=TODAY,
    )
    defaults.update(overrides)
    task_id = wiring["task_repo"].create(Task(**defaults))
    this_week_start = week_start(TODAY)
    wiring["schedule_repo"].replace_week(
        this_week_start,
        [ScheduleEntry(id=None, task_id=task_id, week_start=this_week_start,
                        scheduled_date=TODAY, schedule_reason="TEST")],
    )
    return task_id


def test_taskcard_set_selected_changes_style():
    task = Task(id=1, title="X", description="", task_type=TaskType.NORMAL,
                project_id=None, category="Personal", importance=3, urgency=3,
                seriousness=3, effort=1, available_from=None, due_date=None,
                status=TaskStatus.PENDING)
    card = TaskCard(task, None)
    unselected_style = card.styleSheet()
    card.set_selected(True)
    assert card.styleSheet() != unselected_style
    card.set_selected(False)
    assert card.styleSheet() == unselected_style


def test_clicking_a_card_selects_it_in_today_panel(wiring):
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    assert panel.get_selected_task_id() is None
    panel._handle_card_click(task_id)
    assert panel.get_selected_task_id() == task_id


def test_clear_selection_resets_it(wiring):
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    panel._handle_card_click(task_id)

    panel.clear_selection()

    assert panel.get_selected_task_id() is None


def test_nothing_selected_shortcuts_are_a_no_op(wiring):
    """Ctrl+E/D/Delete/Enter must no-op — no fallback to "first card" —
    when nothing is selected."""
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    assert panel.get_selected_task_id() is None
    panel.edit_selected()
    panel.defer_selected()
    panel.cancel_selected()
    panel.activate_selected()

    unchanged = wiring["task_repo"].get_by_id(task_id)
    assert unchanged.status == TaskStatus.SCHEDULED  # untouched


def test_activate_selected_completes_a_pending_task(wiring):
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    panel._handle_card_click(task_id)

    panel.activate_selected()

    completed = wiring["task_repo"].get_by_id(task_id)
    assert completed.status == TaskStatus.COMPLETED


def test_activate_selected_opens_editor_for_completed_task(wiring):
    """The dialog's exec() is monkeypatched to auto-accept — this just
    proves the branch is taken (title unaffected by the no-op accept)
    rather than re-completing an already-completed task."""
    task_id = make_scheduled_task(wiring, status=TaskStatus.COMPLETED, completed_at=TODAY)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    panel._handle_card_click(task_id)

    panel.activate_selected()  # must not raise, must not re-run complete_task's side effects

    task = wiring["task_repo"].get_by_id(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at == TODAY


def test_cancel_selected_cancels_and_clears_selection(wiring):
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    panel._handle_card_click(task_id)

    panel.cancel_selected()

    assert wiring["task_repo"].get_by_id(task_id).status == TaskStatus.CANCELLED
    assert panel.get_selected_task_id() is None


def test_cancelled_task_disappears_from_the_board(wiring):
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    assert panel._list_layout.count() == 2  # one card + the trailing stretch

    wiring["task_service"].cancel_task(task_id)
    panel.refresh()

    # The removed card's widget may still linger un-destroyed until the
    # next real event loop iteration (deleteLater() semantics) — what
    # matters is it's out of the layout, i.e. no longer on the board.
    assert panel._list_layout.count() == 1  # just the trailing stretch


def test_defer_selected_moves_the_task_in_weekly_board(wiring):
    task_id = make_scheduled_task(wiring)
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    board._handle_card_click(task_id)

    board.defer_selected()  # _DeferDialog is auto-accepted with its default (tomorrow)

    moved = wiring["task_repo"].get_by_id(task_id)
    assert moved.current_scheduled_date == TODAY + timedelta(days=1)
    assert moved.times_deferred == 1


def test_selection_does_not_survive_the_task_it_pointed_to_disappearing(wiring):
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    panel._handle_card_click(task_id)
    assert panel.get_selected_task_id() == task_id

    wiring["task_service"].cancel_task(task_id)
    panel.refresh()

    assert panel.get_selected_task_id() is None
