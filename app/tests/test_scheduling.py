"""Unit tests for core.scheduling_engine. See spec §54."""

from datetime import date, timedelta

from app.config.settings import Capacity, DEFAULT_WEEKLY_CAPACITY, UTILIZATION_TARGET
from app.core.scheduling_engine import FIXED_EVENT, generate_weekly_schedule
from app.models.fixed_event import FixedEvent
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
        available_from=None,
        due_date=None,
        status=TaskStatus.PENDING,
    )
    defaults.update(overrides)
    return Task(**defaults)


def flatten(schedule):
    return [p for placements in schedule.values() for p in placements]


# - tasks cannot be scheduled before available_from
def test_task_not_scheduled_before_available_from():
    task = make_task(id=1, available_from=DAYS[3], due_date=None)
    schedule = generate_weekly_schedule([task], [], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert placement.date >= DAYS[3]


# - tasks cannot be scheduled after due_date
def test_task_not_scheduled_after_due_date():
    task = make_task(id=1, available_from=None, due_date=DAYS[1])
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
        make_task(id=i, effort=2, available_from=MONDAY, due_date=DAYS[6])
        for i in range(1, 8)
    ]
    schedule = generate_weekly_schedule(tasks, [], MONDAY, DEFAULT_WEEKLY_CAPACITY)
    days_used = {p.date for p in flatten(schedule) if p.task_id is not None}
    assert len(days_used) > 1


# - scheduler preserves slack (does not exceed UTILIZATION_TARGET)
def test_scheduler_preserves_slack_under_capacity():
    tasks = [
        make_task(id=i, effort=1, available_from=MONDAY, due_date=DAYS[6])
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
        available_from=MONDAY, due_date=MONDAY,
    )
    low_priority_tasks = [
        make_task(id=i, importance=1, urgency=1, seriousness=1, effort=1,
                   available_from=MONDAY, due_date=DAYS[4])
        for i in range(2, 7)
    ]
    schedule = generate_weekly_schedule(
        [critical] + low_priority_tasks, [], MONDAY, [Capacity.LOW] * 7
    )
    critical_placement = next(p for p in flatten(schedule) if p.task_id == 1)
    assert critical_placement.date == MONDAY
    assert critical_placement.overcommitted is False
