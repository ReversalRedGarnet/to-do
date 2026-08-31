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

# Scheduling reason constants (spec §37)
DEADLINE_APPROACHING = "DEADLINE_APPROACHING"
HIGH_PRIORITY = "HIGH_PRIORITY"
BALANCE_LOAD = "BALANCE_LOAD"
PROJECT_PROGRESS = "PROJECT_PROGRESS"
RECOVER_FROM_MISSED_TASK = "RECOVER_FROM_MISSED_TASK"
FIXED_EVENT = "FIXED_EVENT"
USER_SELECTED = "USER_SELECTED"


def generate_weekly_schedule(tasks, fixed_events, week_start_date, capacities):
    """Returns a dict of date -> list of scheduled task placements."""
    raise NotImplementedError


def rebalance_after_missed_task(missed_task, remaining_week_state):
    """Recovery logic — see spec §39. Must not simply pile onto today."""
    raise NotImplementedError
