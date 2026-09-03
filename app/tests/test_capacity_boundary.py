"""Hardening pass, item 1: capacity boundary regression coverage.

Guards the two protected constants (Capacity.LOW/MEDIUM/HIGH = 3/6/9 and
UTILIZATION_TARGET = 0.75 in app/config/settings.py) against ever being
shadowed or diluted by the Phase 6 week-generation knobs (aggressiveness,
weekend-allowed, low-priority auto-move). Covers all three capacity
levels: LOW (Sunday in DEFAULT_WEEKLY_CAPACITY), MEDIUM (Monday-Friday),
HIGH (Saturday)."""

import math
from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from app.config.settings import Capacity, UTILIZATION_TARGET
from app.core.date_service import week_start
from app.core.scheduling_engine import generate_weekly_schedule
from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.settings_repository import SettingsRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.schedule_service import ScheduleService
from app.services.settings_service import SettingsService
from app.services.task_service import TaskService
from app.ui.weekly_board import WeeklyBoard

MONDAY = date(2026, 6, 15)
DAYS = [MONDAY + timedelta(days=i) for i in range(7)]

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
    settings_repo = SettingsRepository(conn)
    task_service = TaskService(task_repo, NullNotificationService())
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo, settings_repo)
    settings_service = SettingsService(settings_repo)
    return dict(task_repo=task_repo, schedule_repo=schedule_repo, category_repo=category_repo,
                task_service=task_service, schedule_service=schedule_service,
                settings_service=settings_service)


def make_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=None,
        status=TaskStatus.PENDING, created_at=WEEK_START,
    )
    defaults.update(overrides)
    return wiring["task_repo"].create(Task(**defaults))


def seed_scheduled_load(wiring, day, count):
    """Directly seeds `count` effort-1 tasks scheduled on `day` — mimics
    what dragging several cards onto one day, or a Generate Week run,
    would leave behind, without going through either code path so the
    test isolates the load-indicator's own read of the data."""
    entries = []
    for i in range(count):
        task_id = make_task(wiring, title=f"Load {i}", effort=1, status=TaskStatus.SCHEDULED,
                             current_scheduled_date=day)
        entries.append(ScheduleEntry(id=None, task_id=task_id, week_start=WEEK_START,
                                      scheduled_date=day, schedule_reason="TEST"))
    wiring["schedule_repo"].replace_week(WEEK_START, entries)


# --- 1. Core allocator: OVERCOMMITTED boundary is exactly
#        capacity.value * UTILIZATION_TARGET, for all three levels ---

@pytest.mark.parametrize("level", [Capacity.LOW, Capacity.MEDIUM, Capacity.HIGH])
def test_overcommitted_boundary_tracks_capacity_and_utilization_constants(level):
    budget = level.value * UTILIZATION_TARGET
    n_that_fit = math.floor(budget)
    # One task above what the budget allows must tip into OVERCOMMITTED —
    # using default utilization_target (not passed explicitly), i.e. the
    # v1 constant, and effort-1 tasks (cost 1 unit each) confined to a
    # single day so every placement lands on the same day.
    tasks = [
        Task(id=i + 1, title=f"T{i}", description="", task_type=TaskType.NORMAL,
             project_id=None, category="Personal", importance=3, urgency=3,
             seriousness=3, effort=1, due_date=MONDAY,
             status=TaskStatus.PENDING, created_at=MONDAY)
        for i in range(n_that_fit + 1)
    ]
    capacities = [level] * 7

    schedule = generate_weekly_schedule(tasks, [], MONDAY, capacities)

    placements = schedule[MONDAY]
    assert len(placements) == n_that_fit + 1
    assert sum(1 for p in placements if p.overcommitted) == 1
    assert sum(1 for p in placements if not p.overcommitted) == n_that_fit


def test_capacity_and_utilization_constants_survive_a_generate_call_unchanged():
    """A future change that tried to "adapt" the constants per-run (e.g.
    aggressiveness silently reassigning Capacity or UTILIZATION_TARGET
    instead of threading a local override through) would be caught here."""
    before = (Capacity.LOW.value, Capacity.MEDIUM.value, Capacity.HIGH.value, UTILIZATION_TARGET)

    generate_weekly_schedule([], [], MONDAY, [Capacity.MEDIUM] * 7,
                              utilization_target=0.99, weekend_allowed=False)

    after = (Capacity.LOW.value, Capacity.MEDIUM.value, Capacity.HIGH.value, UTILIZATION_TARGET)
    assert before == after == (3, 6, 9, 0.75)


# --- 2. ScheduleService.capacity_for_day is driven by the same protected
#        constants and is never modulated by the Phase 6 week-gen knobs ---

def test_capacity_for_day_matches_default_weekly_capacity_for_all_three_levels(wiring):
    service = wiring["schedule_service"]
    assert service.capacity_for_day(WEEK_START) == Capacity.MEDIUM       # Monday
    assert service.capacity_for_day(WEEK_START + timedelta(days=5)) == Capacity.HIGH   # Saturday
    assert service.capacity_for_day(WEEK_START + timedelta(days=6)) == Capacity.LOW    # Sunday


def test_capacity_for_day_is_unaffected_by_week_generation_settings(wiring):
    before = (
        wiring["schedule_service"].capacity_for_day(WEEK_START),
        wiring["schedule_service"].capacity_for_day(WEEK_START + timedelta(days=5)),
        wiring["schedule_service"].capacity_for_day(WEEK_START + timedelta(days=6)),
    )

    wiring["settings_service"].update(
        week_gen_aggressiveness="aggressive",
        week_gen_weekend_allowed=False,
        week_gen_allow_low_priority_automove=False,
    )

    after = (
        wiring["schedule_service"].capacity_for_day(WEEK_START),
        wiring["schedule_service"].capacity_for_day(WEEK_START + timedelta(days=5)),
        wiring["schedule_service"].capacity_for_day(WEEK_START + timedelta(days=6)),
    )
    assert after == before == (Capacity.MEDIUM, Capacity.HIGH, Capacity.LOW)


def test_preview_week_overcommitted_boundary_matches_capacity_constants_at_default_settings(wiring, monkeypatch):
    """At default week-gen settings (standard aggressiveness, weekend
    allowed, auto-move allowed) Generate Week's overload behavior must be
    driven by exactly the same capacity*utilization budget as the core
    allocator test above — Monday is MEDIUM(6), budget 4.5.

    All 5 tasks are confined to WEEK_START (Monday) itself, so "today"
    must be pinned there too — otherwise the audit fix #3 elapsed-day
    filter would (correctly, but irrelevantly to what this test checks)
    exclude Monday once the suite runs past it."""
    from app.core import date_service
    monkeypatch.setattr(date_service, "today", lambda: WEEK_START)
    for _ in range(5):
        make_task(wiring, effort=1, due_date=WEEK_START)

    plan = wiring["schedule_service"].preview_week(WEEK_START)

    placements = [p for placements in plan.schedule.values() for p in placements if p.task_id is not None]
    assert len(placements) == 5
    assert sum(1 for p in placements if p.overcommitted) == 1
    assert sum(1 for p in placements if not p.overcommitted) == 4


# --- 3. UI load indicator: reads the raw capacity constant, colors off
#        it, and is untouched by the new week-generation settings ---

@pytest.mark.parametrize("offset,level,under,at_target,over", [
    (0, Capacity.MEDIUM, 4, 6, 7),   # Monday
    (5, Capacity.HIGH, 6, 9, 10),    # Saturday
    (6, Capacity.LOW, 2, 3, 4),      # Sunday
])
def test_load_indicator_reflects_raw_capacity_constant_at_each_level(wiring, offset, level, under, at_target, over):
    day = WEEK_START + timedelta(days=offset)
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])

    seed_scheduled_load(wiring, day, under)
    board.refresh()
    label = board._load_labels[day]
    assert label.text() == f"{under}/{level.value} load"
    assert "#c62828" not in label.styleSheet() and "#ef6c00" not in label.styleSheet()

    seed_scheduled_load(wiring, day, at_target)
    board.refresh()
    label = board._load_labels[day]
    assert label.text() == f"{at_target}/{level.value} load"
    assert "#ef6c00" in label.styleSheet()  # over the 0.75 target, still <= raw capacity

    seed_scheduled_load(wiring, day, over)
    board.refresh()
    label = board._load_labels[day]
    assert label.text() == f"{over}/{level.value} load"
    assert "#c62828" in label.styleSheet()  # over raw capacity itself


def test_load_indicator_is_unaffected_by_week_generation_settings(wiring):
    day = WEEK_START  # Monday, MEDIUM = 6
    seed_scheduled_load(wiring, day, 7)  # over capacity -> red, regardless of settings below
    board = WeeklyBoard(wiring["task_service"], wiring["schedule_service"], wiring["category_repo"])
    board.refresh()
    before_text = board._load_labels[day].text()
    before_style = board._load_labels[day].styleSheet()

    wiring["settings_service"].update(
        week_gen_aggressiveness="relaxed",
        week_gen_weekend_allowed=False,
        week_gen_allow_low_priority_automove=False,
    )
    board.refresh()

    assert board._load_labels[day].text() == before_text == "7/6 load"
    assert board._load_labels[day].styleSheet() == before_style
    assert "#c62828" in board._load_labels[day].styleSheet()
