"""Phase 3: ScheduleService.preview_week / apply_plan / undo_plan.

Confirms: (1) locked/manual_override tasks are excluded from reassignment
and kept at their existing date, (2) apply_plan+undo_plan round-trip both
the task_schedule rows and the affected tasks' status/dates exactly, and
(3) generate_week's existing external contract (mutates immediately,
returns the placement dict) is unchanged now that it's built on top of
preview_week/apply_plan."""

from datetime import date, timedelta

import pytest

from app.database.db import get_connection, initialize_database
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType
from app.services.schedule_service import ScheduleService

MONDAY = date(2026, 6, 15)
DAYS = [MONDAY + timedelta(days=i) for i in range(7)]


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    """generate_weekly_schedule now excludes days before "today" from new
    placements (audit fix #3) — pin today to the start of the fixed MONDAY
    week these tests plan around, so none of that week is treated as
    already elapsed relative to whatever date the suite actually runs on."""
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
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    return dict(task_repo=task_repo, schedule_repo=schedule_repo, schedule_service=schedule_service)


def make_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=DAYS[6],
        status=TaskStatus.PENDING, created_at=MONDAY,
    )
    defaults.update(overrides)
    return wiring["task_repo"].create(Task(**defaults))


def schedule_directly(wiring, task_id, on_date, *, locked=False, manual_override=False):
    """Seeds a task_schedule row bypassing ScheduleRepository's own
    write paths (which always set locked=0 or manual_override=1), so
    tests can construct the exact locked/manual_override combination
    they need to verify against."""
    conn = wiring["schedule_repo"]._conn
    conn.execute(
        """
        INSERT INTO task_schedule (task_id, week_start, scheduled_date, schedule_reason, manual_override, locked)
        VALUES (?, ?, ?, 'TEST', ?, ?)
        """,
        (task_id, MONDAY.isoformat(), on_date.isoformat(), int(manual_override), int(locked)),
    )
    conn.commit()


def test_preview_excludes_locked_task_from_reassignment(wiring):
    locked_id = make_task(wiring, effort=1)
    schedule_directly(wiring, locked_id, DAYS[3], locked=True)

    plan = wiring["schedule_service"].preview_week(MONDAY)

    assert locked_id in plan.protected_task_ids
    placement = next(p for placements in plan.schedule.values() for p in placements if p.task_id == locked_id)
    assert placement.date == DAYS[3]


def test_preview_excludes_manually_overridden_task_from_reassignment(wiring):
    moved_id = make_task(wiring, effort=1)
    schedule_directly(wiring, moved_id, DAYS[4], manual_override=True)

    plan = wiring["schedule_service"].preview_week(MONDAY)

    assert moved_id in plan.protected_task_ids
    placement = next(p for placements in plan.schedule.values() for p in placements if p.task_id == moved_id)
    assert placement.date == DAYS[4]


def test_apply_plan_never_touches_a_locked_row(wiring):
    locked_id = make_task(wiring, effort=1)
    schedule_directly(wiring, locked_id, DAYS[3], locked=True)
    other_id = make_task(wiring, effort=1)  # ordinary task, freely placed

    plan = wiring["schedule_service"].preview_week(MONDAY)
    wiring["schedule_service"].apply_plan(plan)

    rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(MONDAY)}
    assert rows[locked_id].scheduled_date == DAYS[3]
    assert rows[locked_id].locked is True
    assert other_id in rows


def test_apply_plan_schedules_and_undo_restores_prior_pending_state(wiring):
    task_id = make_task(wiring, effort=1)
    task_before = wiring["task_repo"].get_by_id(task_id)
    assert task_before.status == TaskStatus.PENDING

    plan = wiring["schedule_service"].preview_week(MONDAY)
    snapshot = wiring["schedule_service"].apply_plan(plan)

    scheduled = wiring["task_repo"].get_by_id(task_id)
    assert scheduled.status == TaskStatus.SCHEDULED
    assert scheduled.current_scheduled_date is not None

    wiring["schedule_service"].undo_plan(snapshot)

    restored = wiring["task_repo"].get_by_id(task_id)
    assert restored.status == TaskStatus.PENDING
    assert restored.current_scheduled_date is None
    assert wiring["schedule_repo"].get_week(MONDAY) == []


def test_undo_restores_a_task_that_was_previously_scheduled_elsewhere(wiring):
    task_id = make_task(wiring, effort=1)
    schedule_directly(wiring, task_id, DAYS[1])  # freely re-placeable, not protected
    task = wiring["task_repo"].get_by_id(task_id)
    task.status = TaskStatus.SCHEDULED
    task.current_scheduled_date = DAYS[1]
    wiring["task_repo"].update(task)

    plan = wiring["schedule_service"].preview_week(MONDAY)
    snapshot = wiring["schedule_service"].apply_plan(plan)
    wiring["schedule_service"].undo_plan(snapshot)

    restored_rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(MONDAY)}
    assert restored_rows[task_id].scheduled_date == DAYS[1]
    restored_task = wiring["task_repo"].get_by_id(task_id)
    assert restored_task.current_scheduled_date == DAYS[1]


def test_generate_week_external_contract_is_unchanged(wiring):
    task_id = make_task(wiring, effort=1)

    schedule = wiring["schedule_service"].generate_week(MONDAY)

    placements = [p for placements in schedule.values() for p in placements]
    assert any(p.task_id == task_id for p in placements)
    persisted = wiring["schedule_repo"].get_week(MONDAY)
    assert any(e.task_id == task_id for e in persisted)


def test_generate_week_on_a_thursday_never_places_new_work_on_mon_tue_wed(wiring, monkeypatch):
    """Audit fix #3, exercised through the actual service entry point
    Generate Week uses (not just the core allocator directly): running
    Generate Week mid-week must not place any task on an already-elapsed
    day of the current week."""
    from app.core import date_service
    thursday = DAYS[3]
    monkeypatch.setattr(date_service, "today", lambda: thursday)
    task_ids = [make_task(wiring, effort=1) for _ in range(5)]

    schedule = wiring["schedule_service"].generate_week(MONDAY)

    placements = [p for placements in schedule.values() for p in placements if p.task_id is not None]
    assert len(placements) == len(task_ids)
    assert all(p.date >= thursday for p in placements)
    assert not any(p.date in (MONDAY, DAYS[1], DAYS[2]) for p in placements)
