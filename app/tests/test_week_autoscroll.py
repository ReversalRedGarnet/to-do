"""WeeklyBoard.scroll_to_first_active_day — jump the (Monday-Sunday, still
computed exactly as before) week view to the first day, starting from
today, that has scheduled tasks, when today itself has none. Purely a
scroll-position behavior: never touches what generate_week schedules or
persists (see weekly_board.py's docstring on the method)."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

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
from app.ui.weekly_board import WeeklyBoard

TODAY = date.today()
WEEK_START = week_start(TODAY)


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
    return dict(task_repo=task_repo, schedule_repo=schedule_repo, category_repo=category_repo,
                task_service=task_service, schedule_service=schedule_service)


def make_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=None,
        status=TaskStatus.SCHEDULED, created_at=WEEK_START,
    )
    defaults.update(overrides)
    return wiring["task_repo"].create(Task(**defaults))


def schedule_on(wiring, task_id, day):
    wiring["schedule_repo"].upsert_task_day(task_id, WEEK_START, day, "TEST", manual_override=False)


def build_board(wiring):
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    board._scroll_area.ensureWidgetVisible = MagicMock()
    return board


def is_last_day_of_week():
    return TODAY == WEEK_START + timedelta(days=6)


@pytest.mark.skipif(is_last_day_of_week(), reason="test needs at least one day after today this week")
def test_scrolls_to_first_later_day_with_tasks_when_today_is_empty(wiring):
    later_day = WEEK_START + timedelta(days=6)  # Sunday — always >= today unless today is Sunday
    task_id = make_task(wiring)
    schedule_on(wiring, task_id, later_day)

    board = build_board(wiring)
    board._scroll_area.ensureWidgetVisible.reset_mock()  # ignore the __init__-time call
    board.scroll_to_first_active_day()

    board._scroll_area.ensureWidgetVisible.assert_called_once_with(board._column_widgets[later_day])


def test_does_not_scroll_when_today_has_tasks(wiring):
    task_id = make_task(wiring)
    schedule_on(wiring, task_id, TODAY)

    board = build_board(wiring)
    board._scroll_area.ensureWidgetVisible.reset_mock()
    board.scroll_to_first_active_day()

    board._scroll_area.ensureWidgetVisible.assert_not_called()


def test_does_not_scroll_when_no_day_this_week_has_tasks(wiring):
    board = build_board(wiring)
    board._scroll_area.ensureWidgetVisible.reset_mock()
    board.scroll_to_first_active_day()

    board._scroll_area.ensureWidgetVisible.assert_not_called()


def test_cancelled_tasks_on_a_day_do_not_count_as_active(wiring):
    task_id = make_task(wiring, status=TaskStatus.CANCELLED)
    schedule_on(wiring, task_id, TODAY)

    board = build_board(wiring)
    board._scroll_area.ensureWidgetVisible.reset_mock()
    board.scroll_to_first_active_day()

    board._scroll_area.ensureWidgetVisible.assert_not_called()
