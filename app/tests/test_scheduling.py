"""Unit tests for core.scheduling_engine. See spec §54."""

from datetime import date, timedelta

from app.config.settings import Capacity, DEFAULT_WEEKLY_CAPACITY, UTILIZATION_TARGET
from app.core.scheduling_engine import (
    FIXED_EVENT,
    USER_SELECTED,
    diff_week_plan,
    generate_weekly_schedule,
)
from app.models.fixed_event import FixedEvent
from app.models.schedule import ScheduleEntry
from app.models.task import Task, TaskStatus, TaskType

MONDAY = date(2026, 6, 15)  # a Monday
DAYS = [MONDAY + timedelta(days=i) for i in range(7)]


def make_task(**overrides):
    defaults = dict(
        id=1,
        title="Task",
        description="",
        task_type=TaskType.NORMAL,
        project_id=None,
        category="Personal",
        importance=3,
        urgency=3,
        seriousness=3,
        effort=1,
        due_date=None,
        status=TaskStatus.PENDING,
    )
    defaults.update(overrides)
    return Task(**defaults)


def flatten(schedule):
    return [p for placements in schedule.values() for p in placements]


# - tasks cannot be scheduled after due_date
def test_task_not_scheduled_after_due_date():
    task = make_task(id=1, due_date=DAYS[1])
    schedule = generate_weekly_schedule([task], [], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert placement.date <= DAYS[1]


# - fixed events remain fixed
def test_fixed_events_remain_fixed():
    event = FixedEvent(id=99, title="Tutoring", description="", event_date=DAYS[2],
                        capacity_cost=2)
    schedule = generate_weekly_schedule([], [event], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    placements = schedule[DAYS[2]]
    assert len(placements) == 1
    assert placements[0].fixed_event_id == 99
    assert placements[0].reason == FIXED_EVENT
    assert placements[0].date == DAYS[2]


def test_fixed_event_consumes_capacity_leaving_less_room_for_tasks():
    event = FixedEvent(id=99, title="Tutoring", description="", event_date=MONDAY,
                        capacity_cost=4)  # Monday budget is 6*0.75=4.5, leaving 0.5
    task = make_task(id=1, effort=2)  # cost 2, does not fit in remaining 0.5
    schedule = generate_weekly_schedule([task], [event], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert placement.date != MONDAY


# - tasks distribute across days
def test_tasks_distribute_across_days():
    tasks = [
        make_task(id=i, effort=2, due_date=DAYS[6])
        for i in range(1, 8)
    ]
    schedule = generate_weekly_schedule(tasks, [], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    days_used = {p.date for p in flatten(schedule) if p.task_id is not None}
    assert len(days_used) > 1


# - scheduler preserves slack (does not exceed UTILIZATION_TARGET)
def test_scheduler_preserves_slack_under_capacity():
    tasks = [
        make_task(id=i, effort=1, due_date=DAYS[6])
        for i in range(1, 6)  # well under total weekly capacity
    ]
    schedule = generate_weekly_schedule(tasks, [], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    capacity_units = [c.value for c in DEFAULT_WEEKLY_CAPACITY]
    for i, d in enumerate(DAYS):
        used = sum(p.capacity_used for p in schedule[d] if not p.overcommitted)
        assert used <= capacity_units[i] * UTILIZATION_TARGET + 1e-9


# - large tasks can span multiple days (v1: not split, but still placed
#   with OVERCOMMITTED flagged on the day with the most slack when it
#   exceeds every single day's target budget)
def test_oversized_task_still_placed_and_flagged_overcommitted():
    huge = make_task(id=1, effort=5)  # cost 8; every day's target budget < 8
    schedule = generate_weekly_schedule([huge], [], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    placements = [p for p in flatten(schedule) if p.task_id == 1]
    assert len(placements) == 1
    assert placements[0].overcommitted is True
    assert placements[0].date == DAYS[5]  # Saturday has the most slack (HIGH capacity)


# - low-priority work does not crowd out imminent critical work
def test_low_priority_work_does_not_crowd_out_critical_task():
    critical = make_task(
        id=1, importance=5, urgency=5, seriousness=5, effort=1,
        due_date=MONDAY,
    )
    low_priority_tasks = [
        make_task(id=i, importance=1, urgency=1, seriousness=1, effort=1,
                   due_date=DAYS[4])
        for i in range(2, 7)
    ]
    schedule = generate_weekly_schedule(
        [critical] + low_priority_tasks, [], MONDAY, [Capacity.LOW] * 7
    )
    critical_placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert critical_placement.date == MONDAY
    assert critical_placement.overcommitted is False


# - Phase 3: locked/manually-placed tasks are never reassigned by a rerun
def test_locked_placement_keeps_its_date_and_is_excluded_from_the_pool():
    locked_task = make_task(id=1, effort=1)
    # Note: locked_task is NOT included in `tasks` — ScheduleService is
    # responsible for that exclusion; the core engine just needs to honor
    # the pre-placed date and consume capacity for it.
    other_tasks = [make_task(id=i, effort=1, due_date=DAYS[6]) for i in range(2, 5)]

    schedule = generate_weekly_schedule(
        other_tasks, [], MONDAY, DEFAULT_WEEKLY_CAPACITY,
        locked_placements=[(locked_task, DAYS[4])],
    )

    locked_placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert locked_placement.date == DAYS[4]
    assert locked_placement.reason == USER_SELECTED


def test_locked_placement_consumes_capacity_leaving_less_room_for_others():
    locked_task = make_task(id=1, effort=5)  # cost 8
    # Wide window so the allocator has somewhere else to go instead of
    # being forced onto Monday and merely flagged overcommitted.
    competitor = make_task(id=2, effort=2, due_date=DAYS[6])

    schedule = generate_weekly_schedule(
        [competitor], [], MONDAY, DEFAULT_WEEKLY_CAPACITY,
        locked_placements=[(locked_task, MONDAY)],  # Monday budget 6*0.75=4.5, 8 already consumed
    )
    competitor_placement = next(p for p in flatten(schedule) if p.task_id == 2)
    assert competitor_placement.date != MONDAY
    assert competitor_placement.overcommitted is False


def test_weekend_disallowed_keeps_new_work_off_saturday_and_sunday():
    tasks = [
        make_task(id=i, effort=2, due_date=DAYS[6])
        for i in range(1, 8)  # more work than Mon-Fri MEDIUM capacity comfortably holds
    ]
    schedule = generate_weekly_schedule(
        tasks, [], MONDAY, DEFAULT_WEEKLY_CAPACITY, weekend_allowed=False,
    )
    days_used = {p.date for p in flatten(schedule) if p.task_id is not None}
    assert DAYS[5] not in days_used  # Saturday
    assert DAYS[6] not in days_used  # Sunday


def test_custom_utilization_target_is_honored():
    tasks = [make_task(id=i, effort=1, due_date=DAYS[0]) for i in range(1, 4)]
    schedule = generate_weekly_schedule(
        tasks, [], MONDAY, DEFAULT_WEEKLY_CAPACITY, utilization_target=0.1,
    )
    # MEDIUM=6 * 0.1 = 0.6 budget on Monday — cost-1 tasks can't fit, all overcommitted
    placements = [p for p in flatten(schedule) if p.task_id is not None]
    assert all(p.overcommitted for p in placements)


# - audit fix #3: elapsed days of the current week are never eligible for new work
def test_today_excludes_already_elapsed_days_from_new_placements():
    thursday = DAYS[3]
    tasks = [make_task(id=i, due_date=None) for i in range(1, 4)]

    schedule = generate_weekly_schedule(tasks, [], MONDAY, DEFAULT_WEEKLY_CAPACITY, today=thursday)

    placements = flatten(schedule)
    assert len(placements) == 3
    assert all(p.date >= thursday for p in placements)
    assert not any(p.date in (MONDAY, DAYS[1], DAYS[2]) for p in placements)  # Mon/Tue/Wed


def test_today_leaves_locked_placements_and_fixed_events_on_elapsed_days_untouched():
    """Locked/manual_override rows and fixed events are never reassigned
    by this function regardless — only *new* work is affected by the
    elapsed-day filter."""
    locked_task = make_task(id=1, effort=1)
    fixed = FixedEvent(id=1, title="Standup", description="", event_date=MONDAY, capacity_cost=1)
    thursday = DAYS[3]

    schedule = generate_weekly_schedule(
        [], [fixed], MONDAY, DEFAULT_WEEKLY_CAPACITY,
        locked_placements=[(locked_task, MONDAY)], today=thursday,
    )

    monday_placements = schedule[MONDAY]
    assert any(p.task_id == 1 for p in monday_placements)
    assert any(p.fixed_event_id == 1 for p in monday_placements)


def test_today_in_a_future_week_excludes_nothing():
    task = make_task(id=1, due_date=None)
    far_future_today = MONDAY - timedelta(days=30)  # this MONDAY hasn't happened yet

    schedule = generate_weekly_schedule([task], [], MONDAY, DEFAULT_WEEKLY_CAPACITY, today=far_future_today)

    placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert placement.date == MONDAY


def test_today_defaults_to_none_and_preserves_prior_behavior():
    """Existing 4-positional-arg callers (no `today`) must see no
    change — a task due earlier in the week is still placeable there."""
    task = make_task(id=1, due_date=DAYS[1])
    schedule = generate_weekly_schedule([task], [], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert placement.date in (MONDAY, DAYS[1])


# - Phase 3: diff_week_plan pure comparison
def test_diff_week_plan_reports_only_actual_moves():
    old_entries = [
        ScheduleEntry(id=1, task_id=1, week_start=MONDAY, scheduled_date=MONDAY, schedule_reason="TEST"),
        ScheduleEntry(id=2, task_id=2, week_start=MONDAY, scheduled_date=DAYS[1], schedule_reason="TEST"),
    ]
    new_schedule = {
        MONDAY: [_placement(task_id=1, d=MONDAY)],  # unchanged
        DAYS[2]: [_placement(task_id=2, d=DAYS[2])],  # moved from DAYS[1]
        DAYS[3]: [_placement(task_id=3, d=DAYS[3])],  # brand new
    }
    changes = diff_week_plan(old_entries, new_schedule)

    assert len(changes) == 2
    moved = next(c for c in changes if c.task_id == 2)
    assert moved.from_date == DAYS[1] and moved.to_date == DAYS[2]
    added = next(c for c in changes if c.task_id == 3)
    assert added.from_date is None and added.to_date == DAYS[3]


def test_diff_week_plan_flags_locked_and_manual_override_rows_as_protected():
    old_entries = [
        ScheduleEntry(id=1, task_id=1, week_start=MONDAY, scheduled_date=MONDAY,
                       schedule_reason="TEST", locked=True),
    ]
    new_schedule = {DAYS[1]: [_placement(task_id=1, d=DAYS[1])]}
    changes = diff_week_plan(old_entries, new_schedule)
    assert changes[0].protected is True


def _placement(task_id, d):
    from app.core.scheduling_engine import Placement
    return Placement(date=d, reason="TEST", capacity_used=1, task_id=task_id)
