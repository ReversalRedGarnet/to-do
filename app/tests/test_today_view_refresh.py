"""Regression coverage for "newly added tasks don't appear until Generate
Week is run". build_today_sections itself already buckets every active
task with no due_date into Unscheduled (see core/board_view.py) —
the actual defect was that switching sidebar tabs never re-ran
TodayPanel.refresh(), so a task created from anywhere other than Today's
own quick-add box (e.g. the Week view's quick-add) stayed invisible on
the Today tab until some unrelated action happened to trigger a refresh.
Fixed in build_main_window's `_on_sidebar_row_changed`."""

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QListWidget

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.notifications.notification_service import NullNotificationService
from app.services.schedule_service import ScheduleService
from app.services.task_service import TaskService
from app.ui.main_window import TodayPanel, build_main_window
from app.ui.widgets.task_card import TaskCard

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
    project_repo = ProjectRepository(conn)
    category_repo = CategoryRepository(conn)
    task_service = TaskService(task_repo, NullNotificationService())
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    return dict(task_repo=task_repo, category_repo=category_repo, project_repo=project_repo,
                task_service=task_service, schedule_service=schedule_service)


def _unscheduled_task_ids(today_panel) -> set:
    layout = today_panel._unscheduled_section.body_layout
    return {
        layout.itemAt(i).widget().task_id
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), TaskCard)
    }


def test_task_added_via_todays_own_quick_add_appears_without_generate_week(wiring):
    panel = TodayPanel(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    panel._entry._input.setText("Buy groceries")
    panel._entry._submit()

    added_id = next(t.id for t in wiring["task_service"].list_all() if t.title == "Buy groceries")
    assert added_id in _unscheduled_task_ids(panel)


def test_task_added_elsewhere_appears_in_today_after_switching_tabs(wiring):
    """The actual reported bug: a task created while the Today tab isn't
    even active — e.g. via the Week view's own quick-add — must show up
    on the Today tab as soon as it's opened, with no Generate Week run
    and no other incidental refresh in between."""
    window = build_main_window(
        wiring["task_service"], wiring["schedule_service"], wiring["project_repo"], wiring["category_repo"],
    )
    today_panel = window.findChildren(TodayPanel)[0]
    sidebar = window.findChildren(QListWidget)[0]

    added = wiring["task_service"].create_task("Added elsewhere")
    assert added.id not in _unscheduled_task_ids(today_panel)  # stale until the tab is (re)selected

    sidebar.setCurrentRow(1)  # This Week
    sidebar.setCurrentRow(0)  # back to Today — must pick up the new task

    assert added.id in _unscheduled_task_ids(today_panel)
