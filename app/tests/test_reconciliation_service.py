"""Unit tests for services.reconciliation_service.ReconciliationService —
the shared wrapper both main.py (startup) and the mid-session rollover
timer (ui/main_window.py) use around core.state_engine.reconcile."""

from datetime import date, timedelta

import pytest

from app.database.db import get_connection, initialize_database
from app.database.repositories.app_state_repository import AppStateRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.history_repository import HistoryRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType
from app.services.history_service import HistoryService
from app.services.reconciliation_service import ReconciliationService
from app.services.schedule_service import ScheduleService

MONDAY = date(2026, 6, 15)


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
    app_state_repo = AppStateRepository(conn)
    history_repo = HistoryRepository(conn)

    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    history_service = HistoryService(history_repo)
    reconciliation_service = ReconciliationService(
        task_repo, schedule_service, app_state_repo, history_service
    )
    return dict(
        task_repo=task_repo, schedule_repo=schedule_repo, app_state_repo=app_state_repo,
        history_repo=history_repo, reconciliation_service=reconciliation_service,
    )


def make_task(**overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=None,
        status=TaskStatus.SCHEDULED, created_at=MONDAY,
    )
    defaults.update(overrides)
    return Task(**defaults)


def test_first_run_has_nothing_to_replay_and_sets_last_known_date(wiring):
    result = wiring["reconciliation_service"].run(MONDAY)

    assert result.reconciled_dates == []
    assert wiring["app_state_repo"].get_last_known_date() == MONDAY


def test_run_persists_missed_task_state(wiring):
    task_repo = wiring["task_repo"]
    task_id = task_repo.create(make_task())
    wiring["schedule_repo"].replace_week(
        MONDAY,
        [ScheduleEntry(id=None, task_id=task_id, week_start=MONDAY,
                        scheduled_date=MONDAY, schedule_reason="TEST")],
    )
    wiring["app_state_repo"].set_last_known_date(MONDAY)

    tuesday = MONDAY + timedelta(days=1)
    result = wiring["reconciliation_service"].run(tuesday)

    assert result.tasks_marked_missed == [task_id]
    persisted = task_repo.get_by_id(task_id)
    assert persisted.times_ignored == 1
    assert wiring["app_state_repo"].get_last_known_date() == tuesday


def test_run_repairs_scheduled_task_with_no_matching_schedule_row(wiring):
    """Simulates a crash between ScheduleService.generate_week's replace_week
    commit and its per-task status-update commits: a task left SCHEDULED
    with a current_scheduled_date but no task_schedule row to back it up."""
    task_repo = wiring["task_repo"]
    task_id = task_repo.create(make_task(current_scheduled_date=MONDAY))
    # Deliberately no schedule_repo.replace_week call — the row is missing.

    wiring["reconciliation_service"].run(MONDAY)

    repaired = task_repo.get_by_id(task_id)
    assert repaired.status == TaskStatus.PENDING
    assert repaired.current_scheduled_date is None


def test_run_leaves_consistent_scheduled_task_untouched(wiring):
    task_repo = wiring["task_repo"]
    task_id = task_repo.create(make_task(current_scheduled_date=MONDAY))
    wiring["schedule_repo"].replace_week(
        MONDAY,
        [ScheduleEntry(id=None, task_id=task_id, week_start=MONDAY,
                        scheduled_date=MONDAY, schedule_reason="TEST")],
    )

    wiring["reconciliation_service"].run(MONDAY)

    unchanged = task_repo.get_by_id(task_id)
    assert unchanged.status == TaskStatus.SCHEDULED
    assert unchanged.current_scheduled_date == MONDAY


def test_run_rebalances_a_missed_task_instead_of_leaving_it_unscheduled(wiring):
    """Audit fix #2: core.scheduling_engine.rebalance_after_missed_task
    was fully implemented but never called from anywhere — a missed task
    just sat PENDING until the next full Generate Week. `run()` must now
    immediately place it on the least-loaded remaining day this week,
    pushing the lightest lower-priority task already there to a later
    day rather than doing nothing until the next full re-plan."""
    task_repo = wiring["task_repo"]
    tuesday = MONDAY + timedelta(days=1)
    wednesday = MONDAY + timedelta(days=2)

    missed_id = task_repo.create(make_task(due_date=wednesday, effort=1))
    light_id = task_repo.create(make_task(effort=1, importance=1, urgency=1, seriousness=1))
    heavy_id = task_repo.create(make_task(effort=2))
    wiring["schedule_repo"].replace_week(MONDAY, [
        ScheduleEntry(id=None, task_id=missed_id, week_start=MONDAY,
                       scheduled_date=MONDAY, schedule_reason="TEST"),
        ScheduleEntry(id=None, task_id=light_id, week_start=MONDAY,
                       scheduled_date=tuesday, schedule_reason="TEST"),
        ScheduleEntry(id=None, task_id=heavy_id, week_start=MONDAY,
                       scheduled_date=wednesday, schedule_reason="TEST"),
    ])
    wiring["app_state_repo"].set_last_known_date(MONDAY)

    result = wiring["reconciliation_service"].run(tuesday)

    assert result.tasks_marked_missed == [missed_id]

    missed_task = task_repo.get_by_id(missed_id)
    assert missed_task.status == TaskStatus.SCHEDULED
    assert missed_task.current_scheduled_date == tuesday  # the day it was pushed onto

    pushed_task = task_repo.get_by_id(light_id)
    assert pushed_task.current_scheduled_date is not None
    assert pushed_task.current_scheduled_date > tuesday  # bumped to make room, not left in place

    rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(MONDAY)}
    assert rows[missed_id].scheduled_date == tuesday
    assert rows[light_id].scheduled_date == pushed_task.current_scheduled_date
    assert rows[heavy_id].scheduled_date == wednesday  # untouched — not the pushed task


def test_run_skips_rebalance_when_the_missed_tasks_week_has_already_elapsed(wiring):
    """A multi-week gap must not try to rebalance into a week that's
    entirely behind "today" — that stays the full Generate Week's job."""
    task_repo = wiring["task_repo"]
    missed_id = task_repo.create(make_task())
    wiring["schedule_repo"].replace_week(
        MONDAY,
        [ScheduleEntry(id=None, task_id=missed_id, week_start=MONDAY,
                        scheduled_date=MONDAY, schedule_reason="TEST")],
    )
    wiring["app_state_repo"].set_last_known_date(MONDAY)

    next_monday = MONDAY + timedelta(days=7)
    result = wiring["reconciliation_service"].run(next_monday)

    assert missed_id in result.tasks_marked_missed
    restored = task_repo.get_by_id(missed_id)
    assert restored.status == TaskStatus.PENDING  # left for the next Generate Week, not rebalanced
    assert restored.current_scheduled_date is None


def test_run_archives_week_via_history_service_on_boundary_crossing(wiring):
    task_repo = wiring["task_repo"]
    task_id = task_repo.create(make_task())
    wiring["schedule_repo"].replace_week(
        MONDAY,
        [ScheduleEntry(id=None, task_id=task_id, week_start=MONDAY,
                        scheduled_date=MONDAY, schedule_reason="TEST")],
    )
    wiring["app_state_repo"].set_last_known_date(MONDAY)

    next_monday = MONDAY + timedelta(days=7)
    result = wiring["reconciliation_service"].run(next_monday)

    assert len(result.weeks_archived) == 1
    archived = wiring["history_repo"].list_all()
    assert len(archived) == 1
    assert archived[0].week_start == MONDAY
