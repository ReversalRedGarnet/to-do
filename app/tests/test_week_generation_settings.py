"""Phase 6: Week generation settings (aggressiveness, weekend-allowed,
low-priority auto-move) actually affect ScheduleService.preview_week when
not passed explicitly — additive scheduling knobs, never the LOW/MEDIUM/
HIGH capacity constants themselves (see app/config/settings.py)."""

from datetime import date, timedelta

import pytest

from app.database.db import get_connection, initialize_database
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.settings_repository import SettingsRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.task import Task, TaskStatus, TaskType
from app.services.schedule_service import ScheduleService
from app.services.settings_service import SettingsService

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
    settings_repo = SettingsRepository(conn)
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo, settings_repo)
    settings_service = SettingsService(settings_repo)
    return dict(task_repo=task_repo, schedule_repo=schedule_repo,
                schedule_service=schedule_service, settings_service=settings_service)


def make_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=2, due_date=DAYS[6],
        status=TaskStatus.PENDING, created_at=MONDAY,
    )
    defaults.update(overrides)
    return wiring["task_repo"].create(Task(**defaults))


def test_settings_weekend_disallowed_keeps_preview_off_the_weekend(wiring):
    wiring["settings_service"].update(week_gen_weekend_allowed=False)
    tasks = [make_task(wiring, effort=2) for _ in range(7)]

    plan = wiring["schedule_service"].preview_week(MONDAY)

    used_days = {p.date for placements in plan.schedule.values() for p in placements if p.task_id is not None}
    assert DAYS[5] not in used_days
    assert DAYS[6] not in used_days


def _two_cost2_monday_only_tasks(wiring):
    # Monday MEDIUM=6; standard target 0.75 -> budget 4.5 (both cost-2 tasks
    # fit: 2+2=4); relaxed target 0.60 -> budget 3.6 (only the first fits).
    make_task(wiring, id=None, effort=2, due_date=MONDAY, importance=5, urgency=5)
    make_task(wiring, id=None, effort=2, due_date=MONDAY, importance=4, urgency=4)


def test_settings_aggressiveness_relaxed_lowers_effective_target(wiring):
    wiring["settings_service"].update(week_gen_aggressiveness="relaxed")
    _two_cost2_monday_only_tasks(wiring)

    plan = wiring["schedule_service"].preview_week(MONDAY)

    placements = [p for placements in plan.schedule.values() for p in placements if p.task_id is not None]
    assert any(p.overcommitted for p in placements)


def test_settings_aggressiveness_standard_is_the_v1_default_behavior(wiring):
    _two_cost2_monday_only_tasks(wiring)

    plan = wiring["schedule_service"].preview_week(MONDAY)

    placements = [p for placements in plan.schedule.values() for p in placements if p.task_id is not None]
    assert all(not p.overcommitted for p in placements)


def test_low_priority_automove_disabled_protects_an_already_placed_low_priority_task(wiring, conn):
    low_id = make_task(wiring, importance=1, urgency=1, seriousness=1, effort=1)
    conn.execute(
        "INSERT INTO task_schedule (task_id, week_start, scheduled_date, schedule_reason, manual_override, locked) "
        "VALUES (?, ?, ?, 'TEST', 0, 0)",
        (low_id, MONDAY.isoformat(), DAYS[4].isoformat()),
    )
    conn.commit()
    wiring["settings_service"].update(week_gen_allow_low_priority_automove=False)

    plan = wiring["schedule_service"].preview_week(MONDAY)

    assert low_id in plan.protected_task_ids
    placement = next(p for placements in plan.schedule.values() for p in placements if p.task_id == low_id)
    assert placement.date == DAYS[4]  # unchanged


def test_low_priority_automove_disabled_still_places_a_never_scheduled_low_priority_task(wiring):
    wiring["settings_service"].update(week_gen_allow_low_priority_automove=False)
    low_id = make_task(wiring, importance=1, urgency=1, seriousness=1, effort=1)

    plan = wiring["schedule_service"].preview_week(MONDAY)

    assert low_id not in plan.protected_task_ids
    assert any(
        p.task_id == low_id for placements in plan.schedule.values() for p in placements
    )


def test_apply_plan_preserves_a_low_priority_protected_non_locked_row(wiring, conn):
    low_id = make_task(wiring, importance=1, urgency=1, seriousness=1, effort=1)
    conn.execute(
        "INSERT INTO task_schedule (task_id, week_start, scheduled_date, schedule_reason, manual_override, locked) "
        "VALUES (?, ?, ?, 'TEST', 0, 0)",
        (low_id, MONDAY.isoformat(), DAYS[4].isoformat()),
    )
    conn.commit()
    wiring["settings_service"].update(week_gen_allow_low_priority_automove=False)

    plan = wiring["schedule_service"].preview_week(MONDAY)
    wiring["schedule_service"].apply_plan(plan)

    rows = {e.task_id: e for e in wiring["schedule_repo"].get_week(MONDAY)}
    assert rows[low_id].scheduled_date == DAYS[4]
