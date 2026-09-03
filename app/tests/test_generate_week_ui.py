"""Phase 3 UI wiring: the Week view's Generate Week button opens a preview
dialog before anything is persisted, and Apply/Undo round-trip through
the real WeeklyBoard + ScheduleService (not mocked), matching the
technique test_shortcuts_and_theme.py uses for the real build_main_window."""

from datetime import date

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from app.core.date_service import week_start
from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.schedule_service import ScheduleService
from app.services.task_service import TaskService
from app.ui.weekly_board import GenerateWeekPreviewDialog, WeeklyBoard

TODAY = date.today()


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
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)
    category_repo = CategoryRepository(conn)
    task_service = TaskService(task_repo, NullNotificationService())
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    task_repo.create(Task(
        id=None, title="Something to plan", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3, seriousness=3,
        effort=1, due_date=None, status=TaskStatus.PENDING, created_at=TODAY,
    ))
    return dict(task_repo=task_repo, schedule_repo=schedule_repo, category_repo=category_repo,
                task_service=task_service, schedule_service=schedule_service)


def test_run_generate_week_does_not_persist_until_dialog_accepted(wiring, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    board.run_generate_week()

    assert wiring["schedule_repo"].get_week(week_start(TODAY)) == []


def test_accepting_the_preview_applies_and_enables_undo(wiring, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    undo_states = []
    board.undo_available_changed.connect(undo_states.append)
    board.run_generate_week()

    assert wiring["schedule_repo"].get_week(week_start(TODAY)) != []
    assert undo_states == [True]

    board.undo_last_generate()

    assert wiring["schedule_repo"].get_week(week_start(TODAY)) == []
    assert undo_states == [True, False]

    # Two full board rebuilds happened above (apply's refresh + undo's
    # refresh), each queuing deleteLater() on the prior cards — let Qt
    # actually process that queue before the widget tree goes out of
    # scope, rather than leaving it pending for some unrelated later
    # test's event-loop spin to stumble into.
    QTest.qWait(10)


def test_undo_is_a_no_op_when_nothing_to_undo(wiring):
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    board.undo_last_generate()  # must not raise


def test_preview_dialog_discloses_undo_is_session_only(wiring):
    """Hardening pass item 2: the preview dialog is where a user commits
    to Apply, so this is where the session-only undo tradeoff must be
    disclosed up front, not left for them to discover after a restart."""
    plan = wiring["schedule_service"].preview_week(week_start(TODAY))

    dialog = GenerateWeekPreviewDialog(plan, task_titles={})

    from PySide6.QtWidgets import QLabel
    texts = " ".join(w.text() for w in dialog.findChildren(QLabel)).lower()
    assert "session" in texts
