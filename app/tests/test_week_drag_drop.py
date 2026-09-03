"""Phase 4: Week view drag-and-drop. Real Qt drag-and-drop isn't reliably
simulated across widgets via QTest mouse events, so these tests call
WeeklyBoard's drop handlers directly — the same technique existing tests
use for _on_defer/_on_edit — which is exactly what a real drop event
delivers to (see _DropColumn.dropEvent in weekly_board.py)."""

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from app.core.date_service import week_start
from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.schedule import ScheduleEntry
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
        status=TaskStatus.PENDING, created_at=WEEK_START,
    )
    defaults.update(overrides)
    return wiring["task_repo"].create(Task(**defaults))


def test_dragging_a_scheduled_task_to_another_day_updates_the_date(wiring):
    task_id = make_task(wiring, status=TaskStatus.SCHEDULED)
    wiring["schedule_repo"].replace_week(WEEK_START, [
        ScheduleEntry(id=None, task_id=task_id, week_start=WEEK_START,
                       scheduled_date=WEEK_START, schedule_reason="TEST"),
    ])
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    target_day = WEEK_START + timedelta(days=2)

    board._on_drop(task_id, target_day)

    rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(WEEK_START)}
    assert rows[task_id].scheduled_date == target_day
    assert rows[task_id].manual_override is True
    task = wiring["task_repo"].get_by_id(task_id)
    assert task.current_scheduled_date == target_day
    assert task.status == TaskStatus.SCHEDULED


def test_dragging_an_unscheduled_task_onto_a_day_schedules_it(wiring):
    task_id = make_task(wiring, status=TaskStatus.PENDING)
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    target_day = WEEK_START + timedelta(days=1)

    board._on_drop(task_id, target_day)

    rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(WEEK_START)}
    assert rows[task_id].scheduled_date == target_day
    task = wiring["task_repo"].get_by_id(task_id)
    assert task.status == TaskStatus.SCHEDULED
    assert task.current_scheduled_date == target_day


def test_dragging_to_unscheduled_clears_the_scheduled_date(wiring):
    task_id = make_task(wiring, status=TaskStatus.SCHEDULED, current_scheduled_date=WEEK_START)
    wiring["schedule_repo"].replace_week(WEEK_START, [
        ScheduleEntry(id=None, task_id=task_id, week_start=WEEK_START,
                       scheduled_date=WEEK_START, schedule_reason="TEST"),
    ])
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    board._on_unschedule(task_id)

    rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(WEEK_START)}
    assert task_id not in rows
    task = wiring["task_repo"].get_by_id(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.current_scheduled_date is None


def test_unscheduled_column_lists_pending_tasks_due_within_the_week(wiring):
    in_week = make_task(wiring, due_date=WEEK_START + timedelta(days=3))
    no_due_date = make_task(wiring, due_date=None)
    far_future = make_task(wiring, due_date=WEEK_START + timedelta(days=30))
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    candidate_ids = {t.id for t in board._unscheduled_candidates(set())}

    assert in_week in candidate_ids
    assert no_due_date in candidate_ids
    assert far_future not in candidate_ids


def test_unscheduled_column_excludes_tasks_already_scheduled_this_week(wiring):
    task_id = make_task(wiring, due_date=WEEK_START + timedelta(days=1))
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    candidate_ids = {t.id for t in board._unscheduled_candidates({task_id})}

    assert task_id not in candidate_ids


# --- Audit item: Lock task to day, wired through the context menu ---

def test_lock_toggle_locks_then_unlocks_a_scheduled_task(wiring):
    task_id = make_task(wiring, status=TaskStatus.SCHEDULED)
    wiring["schedule_repo"].replace_week(WEEK_START, [
        ScheduleEntry(id=None, task_id=task_id, week_start=WEEK_START,
                       scheduled_date=WEEK_START, schedule_reason="TEST"),
    ])
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    board._on_lock_toggle(task_id)
    assert {e.task_id: e for e in wiring["schedule_repo"].get_week(WEEK_START)}[task_id].locked is True

    board._on_lock_toggle(task_id)
    assert {e.task_id: e for e in wiring["schedule_repo"].get_week(WEEK_START)}[task_id].locked is False


def test_dragging_a_locked_task_is_rejected_and_the_lock_survives(wiring):
    """Per the documented "a locked task is never reassigned" contract —
    exercised here through the real drop handler and the real DB-level
    guard on ScheduleRepository.upsert_task_day, not just the pure
    scheduling-engine unit tests."""
    task_id = make_task(wiring, status=TaskStatus.SCHEDULED, current_scheduled_date=WEEK_START)
    wiring["schedule_repo"].replace_week(WEEK_START, [
        ScheduleEntry(id=None, task_id=task_id, week_start=WEEK_START,
                       scheduled_date=WEEK_START, schedule_reason="TEST", locked=True),
    ])
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    target_day = WEEK_START + timedelta(days=2)

    board._on_drop(task_id, target_day)

    rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(WEEK_START)}
    assert rows[task_id].scheduled_date == WEEK_START  # unchanged
    assert rows[task_id].locked is True  # still locked
    task = wiring["task_repo"].get_by_id(task_id)
    assert task.current_scheduled_date == WEEK_START  # task's own field untouched too


def test_locked_task_card_is_not_draggable_and_shows_the_locked_marker():
    from PySide6.QtWidgets import QLabel
    from app.ui.widgets.task_card import TaskCard

    task = Task(
        id=1, title="Locked task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3, seriousness=3,
        effort=1, due_date=None,
        status=TaskStatus.SCHEDULED, created_at=WEEK_START,
    )

    card = TaskCard(task, None, show_lock=True, locked=True)

    assert card._draggable is False
    meta_text = " ".join(w.text() for w in card.findChildren(QLabel))
    assert "Locked" in meta_text
