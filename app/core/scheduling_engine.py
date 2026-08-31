"""
Weekly scheduling engine — day-level allocation, not hourly.

v1 is a deterministic greedy allocator (see ALGORITHM.md):
    1. sort eligible tasks by priority score, descending
    2. walk days Monday -> Sunday, walk tasks in sorted order
    3. place each task on the earliest day within its
       [available_from, due_date] window with capacity remaining under
       UTILIZATION_TARGET
    4. if no day in-window has room, place on the day with the most slack
       in-window anyway and flag OVERCOMMITTED

No backtracking, no lookahead, no fairness reshuffling in v1 — that is
deferred to a v2 load-balancing pass. Keep this function pure and testable:
no direct DB or datetime.now() calls inside the core allocation logic.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from app.config.settings import EFFORT_UNITS, UTILIZATION_TARGET
from app.core.priority_engine import calculate_deadline_pressure, calculate_priority_score
from app.models.task import TaskType

# Scheduling reason constants (spec §37)
DEADLINE_APPROACHING = "DEADLINE_APPROACHING"
HIGH_PRIORITY = "HIGH_PRIORITY"
BALANCE_LOAD = "BALANCE_LOAD"
PROJECT_PROGRESS = "PROJECT_PROGRESS"
RECOVER_FROM_MISSED_TASK = "RECOVER_FROM_MISSED_TASK"
FIXED_EVENT = "FIXED_EVENT"
USER_SELECTED = "USER_SELECTED"

# Deadline pressure at/above this (0-5 scale) is considered "approaching"
# for the purpose of picking a scheduling reason, not for eligibility.
_DEADLINE_APPROACHING_THRESHOLD = 3.5


@dataclass
class Placement:
    date: date
    reason: str
    capacity_used: float
    task_id: Optional[int] = None
    fixed_event_id: Optional[int] = None
    overcommitted: bool = False


def _week_dates(week_start_date: date) -> List[date]:
    return [week_start_date + timedelta(days=i) for i in range(7)]


def _capacity_units(capacities) -> List[float]:
    return [c.value if hasattr(c, "value") else c for c in capacities]


def _eligible_days(task, week_dates: List[date]) -> List[date]:
    return [
        d for d in week_dates
        if (task.available_from is None or d >= task.available_from)
        and (task.due_date is None or d <= task.due_date)
    ]


def _reason_for(task, today: date) -> str:
    if task.task_type == TaskType.PROJECT_CHILD:
        return PROJECT_PROGRESS
    pressure = calculate_deadline_pressure(task.due_date, today)
    if pressure >= _DEADLINE_APPROACHING_THRESHOLD:
        return DEADLINE_APPROACHING
    return HIGH_PRIORITY


def generate_weekly_schedule(tasks, fixed_events, week_start_date, capacities):
    """Returns a dict of date -> list of Placement for every day of the week."""
    week_dates = _week_dates(week_start_date)
    capacity_units = _capacity_units(capacities)
    target_budget = {
        d: capacity_units[i] * UTILIZATION_TARGET for i, d in enumerate(week_dates)
    }

    schedule = {d: [] for d in week_dates}

    for event in fixed_events:
        if event.event_date not in schedule:
            continue
        schedule[event.event_date].append(
            Placement(
                date=event.event_date,
                reason=FIXED_EVENT,
                capacity_used=event.capacity_cost,
                fixed_event_id=event.id,
            )
        )
        target_budget[event.event_date] -= event.capacity_cost

    eligible = [
        (task, _eligible_days(task, week_dates))
        for task in tasks
    ]
    eligible = [(task, days) for task, days in eligible if days]
    eligible.sort(key=lambda pair: calculate_priority_score(pair[0], week_start_date), reverse=True)

    for task, days in eligible:
        cost = EFFORT_UNITS[task.effort]
        reason = _reason_for(task, week_start_date)

        chosen_day = None
        for d in days:
            if target_budget[d] >= cost:
                chosen_day = d
                break

        overcommitted = chosen_day is None
        if chosen_day is None:
            chosen_day = max(days, key=lambda d: target_budget[d])

        target_budget[chosen_day] -= cost
        schedule[chosen_day].append(
            Placement(
                date=chosen_day,
                reason=reason,
                capacity_used=cost,
                task_id=task.id,
                overcommitted=overcommitted,
            )
        )

    return schedule


def rebalance_after_missed_task(missed_task, remaining_week_state):
    """
    Recovery logic (spec §39). `remaining_week_state` is a dict of
    date -> list[Placement] for the days from tomorrow through the end of
    the week (today/past days are already closed out by state_engine).

    Does NOT simply append the missed task to the busiest remaining day.
    Instead: find the day with the most slack among the task's still-valid
    eligible days, and if that day is already at/over its target budget,
    free room by pushing the single lowest-priority, non-locked, non-fixed
    placement on that day to the next day with slack (cascading at most
    once per rebalance — no unbounded reshuffling, consistent with v1's
    "no fairness reshuffling" scope).
    """
    days = sorted(remaining_week_state.keys())
    eligible_days = [
        d for d in days
        if (missed_task.available_from is None or d >= missed_task.available_from)
        and (missed_task.due_date is None or d <= missed_task.due_date)
    ]
    if not eligible_days:
        eligible_days = days
    if not eligible_days:
        return remaining_week_state

    cost = EFFORT_UNITS[missed_task.effort]

    def day_load(d):
        return sum(p.capacity_used for p in remaining_week_state[d])

    target_day = min(eligible_days, key=day_load)

    placements = remaining_week_state[target_day]
    if placements:
        lightest = min(
            (p for p in placements if p.task_id is not None and not p.overcommitted),
            key=lambda p: p.capacity_used,
            default=None,
        )
        later_days = [d for d in days if d > target_day]
        if lightest is not None and later_days:
            next_day = min(later_days, key=day_load)
            placements.remove(lightest)
            lightest.date = next_day
            lightest.reason = BALANCE_LOAD
            remaining_week_state[next_day].append(lightest)

    remaining_week_state[target_day].append(
        Placement(
            date=target_day,
            reason=RECOVER_FROM_MISSED_TASK,
            capacity_used=cost,
            task_id=missed_task.id,
        )
    )
    return remaining_week_state
