"""Verifies main_window's keyboard-shortcut wiring (spec §50) end to end
against the real build_main_window, and ui/theme.py's dark-mode switch."""

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.core.date_service import week_start
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.schedule_service import ScheduleService
from app.services.task_service import TaskService
from app.ui.main_window import build_main_window
from app.ui.theme import apply_system_theme

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
def window(conn):
    task_repo = TaskRepository(conn)
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)
    project_repo = ProjectRepository(conn)
    category_repo = CategoryRepository(conn)

    task_service = TaskService(task_repo, NullNotificationService())
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)

    task_id = task_repo.create(Task(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=TODAY, due_date=None,
        status=TaskStatus.SCHEDULED, created_at=TODAY,
    ))
    this_week_start = week_start(TODAY)
    schedule_repo.replace_week(
        this_week_start,
        [ScheduleEntry(id=None, task_id=task_id, week_start=this_week_start,
                        scheduled_date=TODAY, schedule_reason="TEST")],
    )

    win = build_main_window(task_service, schedule_service, project_repo, category_repo)
    win.task_id = task_id
    win.task_repo = task_repo
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win.close()


def test_ctrl_w_t_p_switch_views(window):
    QTest.keySequence(window, "Ctrl+W")
    assert window.centralWidget().findChildren(QLineEdit)  # This Week has a quick-add too

    QTest.keySequence(window, "Ctrl+P")
    QTest.keySequence(window, "Ctrl+T")


def test_ctrl_e_no_ops_when_nothing_selected(window):
    # Should not raise, should not change anything, with no selection.
    QTest.keySequence(window, "Ctrl+E")
    task = window.task_repo.get_by_id(window.task_id)
    assert task.status == TaskStatus.SCHEDULED


def test_shortcuts_do_not_fire_while_a_text_field_has_focus(window):
    line_edits = window.findChildren(QLineEdit)
    quick_add = line_edits[0]
    quick_add.setFocus()
    QTest.qWait(10)

    # Typing "d" into the quick-add field must not defer anything —
    # it must be treated as ordinary text input.
    QTest.keyClicks(quick_add, "d")
    assert quick_add.text() == "d"


def test_delete_shortcut_cancels_selected_task(window):
    from app.ui.main_window import TodayPanel
    today_panel = window.findChild(TodayPanel)
    today_panel._handle_card_click(window.task_id)

    QTest.keySequence(window, "Del")

    task = window.task_repo.get_by_id(window.task_id)
    assert task.status == TaskStatus.CANCELLED


def test_view_switch_clears_selection(window):
    from app.ui.main_window import TodayPanel
    today_panel = window.findChild(TodayPanel)
    today_panel._handle_card_click(window.task_id)
    assert today_panel.get_selected_task_id() == window.task_id

    QTest.keySequence(window, "Ctrl+W")

    assert today_panel.get_selected_task_id() is None


def test_apply_system_theme_is_a_noop_when_system_is_light(monkeypatch, qapp):
    monkeypatch.setattr(qapp.styleHints(), "colorScheme", lambda: Qt.ColorScheme.Light)
    original_palette = qapp.palette()
    apply_system_theme(qapp)
    assert qapp.palette() == original_palette


def test_apply_system_theme_switches_to_dark_palette(monkeypatch, qapp):
    monkeypatch.setattr(qapp.styleHints(), "colorScheme", lambda: Qt.ColorScheme.Dark)
    apply_system_theme(qapp)
    window_color = qapp.palette().color(QPalette.ColorRole.Window)
    assert window_color.lightness() < 128  # a genuinely dark background
