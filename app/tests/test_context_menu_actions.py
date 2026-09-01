"""Phase 7: right-click context menu actions (Delete+Undo, Duplicate,
Move to Project) — drives TodayPanel/WeeklyBoard's handler methods
directly, the same technique existing tests use for _on_defer/_on_edit,
since real right-click QMenu popups can't be driven headlessly."""

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.core.date_service import week_start
from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.project import Project
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.schedule_service import ScheduleService
from app.services.task_service import TaskService
from app.ui.main_window import TodayPanel
from app.ui.weekly_board import WeeklyBoard

TODAY = date.today()
WEEK_START = week_start(TODAY)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def auto_accept_dialogs(monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)


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
    project_repo = ProjectRepository(conn)
    task_service = TaskService(task_repo, NullNotificationService())
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    return dict(task_repo=task_repo, schedule_repo=schedule_repo, category_repo=category_repo,
                project_repo=project_repo, task_service=task_service, schedule_service=schedule_service)


def make_scheduled_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=TODAY, due_date=None,
        status=TaskStatus.SCHEDULED, created_at=TODAY, current_scheduled_date=TODAY,
    )
    defaults.update(overrides)
    task_id = wiring["task_repo"].create(Task(**defaults))
    wiring["schedule_repo"].replace_week(
        WEEK_START,
        [ScheduleEntry(id=None, task_id=task_id, week_start=WEEK_START,
                        scheduled_date=TODAY, schedule_reason="TEST")],
    )
    return task_id


# --- TaskService.delete_task / restore_task ---

def test_delete_task_removes_the_row_and_cascades_schedule_entries(wiring):
    task_id = make_scheduled_task(wiring)

    deleted = wiring["task_service"].delete_task(task_id)

    assert deleted.id == task_id
    assert wiring["task_repo"].get_by_id(task_id) is None
    assert wiring["schedule_repo"].get_week(WEEK_START) == []


def test_restore_task_recreates_it_with_a_new_id(wiring):
    task_id = make_scheduled_task(wiring, title="Bring back")
    deleted = wiring["task_service"].delete_task(task_id)

    restored = wiring["task_service"].restore_task(deleted)

    assert restored.id != task_id
    fetched = wiring["task_repo"].get_by_id(restored.id)
    assert fetched.title == "Bring back"


# --- TodayPanel: delete + undo, duplicate, move to project ---

def test_today_panel_delete_then_undo_restores_the_task_on_the_board(wiring):
    task_id = make_scheduled_task(wiring, title="Restore me")
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    panel._on_delete_requested(task_id)
    assert wiring["task_repo"].get_by_id(task_id) is None
    # The panel is never shown in this test, so isVisible() would be False
    # regardless of setVisible() — isVisibleTo(panel) checks the explicit
    # flag relative to panel itself instead of the whole (unshown) ancestor chain.
    assert panel._undo_delete_button.isVisibleTo(panel) is True

    panel._undo_delete()

    assert panel._undo_delete_button.isVisibleTo(panel) is False
    all_titles = {t.title for t in wiring["task_service"].list_all()}
    assert "Restore me" in all_titles
    restored = next(t for t in wiring["task_service"].list_all() if t.title == "Restore me")
    assert restored.current_scheduled_date == TODAY
    rows = {e.task_id for e in wiring["schedule_repo"].get_week(WEEK_START)}
    assert restored.id in rows


def test_today_panel_duplicate_creates_a_new_pending_copy(wiring):
    task_id = make_scheduled_task(wiring, title="Original", effort=3)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    panel._on_duplicate(task_id)

    all_tasks = wiring["task_service"].list_all()
    copy = next(t for t in all_tasks if t.title == "Original (copy)")
    assert copy.effort == 3
    assert copy.status == TaskStatus.PENDING


def test_move_to_project_dialog_selection_feeds_update_task(wiring):
    """Drives MoveToProjectDialog directly (QDialog.exec is monkeypatched
    globally in this file, so we can't interact with a real modal
    exec()'d dialog) — sets its combo, reads `selected_project_id()`, and
    confirms that value is exactly what `_on_move_to_project`'s accepted
    branch would pass to `TaskService.update_task`."""
    project_id = wiring["project_repo"].create(Project(id=None, name="Launch", description=""))
    task_id = make_scheduled_task(wiring)
    task = wiring["task_repo"].get_by_id(task_id)

    from app.ui.task_editor import MoveToProjectDialog
    dialog = MoveToProjectDialog(task, wiring["project_repo"])
    dialog._project.setCurrentIndex(dialog._project.findData(project_id))
    assert dialog.selected_project_id() == project_id

    wiring["task_service"].update_task(task_id, project_id=dialog.selected_project_id())

    updated = wiring["task_repo"].get_by_id(task_id)
    assert updated.project_id == project_id
    assert updated.task_type == TaskType.PROJECT_CHILD


def test_today_panel_move_to_project_no_op_when_project_repository_not_wired(wiring):
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    panel._on_move_to_project(task_id)  # no project_repository wired -> must not raise, no-op

    assert wiring["task_repo"].get_by_id(task_id).project_id is None


# --- WeeklyBoard: delete + undo, duplicate ---

def test_weekly_board_delete_then_undo_restores_the_row(wiring):
    task_id = make_scheduled_task(wiring, title="Board task")
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    board._on_delete_requested(task_id)
    assert wiring["task_repo"].get_by_id(task_id) is None

    board.undo_last_delete()

    restored = next(t for t in wiring["task_service"].list_all() if t.title == "Board task")
    assert restored.current_scheduled_date == TODAY


def test_weekly_board_undo_delete_is_a_no_op_when_nothing_to_undo(wiring):
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    board.undo_last_delete()  # must not raise


def test_weekly_board_duplicate(wiring):
    task_id = make_scheduled_task(wiring, title="Board original")
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    board._on_duplicate(task_id)

    titles = {t.title for t in wiring["task_service"].list_all()}
    assert "Board original (copy)" in titles


def test_delete_confirmation_declined_keeps_the_task(wiring, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    task_id = make_scheduled_task(wiring)
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    panel._on_delete_requested(task_id)

    assert wiring["task_repo"].get_by_id(task_id) is not None
