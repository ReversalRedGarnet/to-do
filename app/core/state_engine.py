"""
Derives visual color + lifecycle state transitions. Color is NEVER stored
as authoritative state — it is computed from task properties, today's date,
schedule, prior exposure, and completion state (see spec §9).

Also owns midnight/multi-day rollover reconciliation — the single hardest
and most safety-critical piece of this application. Keep it pure (no
datetime.now() calls, no direct DB writes) so it is fully unit-testable;
callers pass in dates and current state, and get back a plan of changes
to apply.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import List


class Color(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    PURPLE = "purple"
    BLUE = "blue"


@dataclass
class ReconciliationResult:
    reconciled_dates: List[date]
    tasks_marked_missed: list
    state_transitions: list  # e.g. (task_id, old_color, new_color)
    weeks_archived: list
    new_today_board: list


def reconcile(last_known_date: date, today: date, db_state) -> ReconciliationResult:
    """
    Replays day-by-day from last_known_date to today (exclusive of today).
    For each intervening date: close out unfinished non-deferred/cancelled
    tasks as missed, apply orange/red transitions, and archive+purge weekly
    history when a replayed day crosses a week boundary. Only after the
    full replay does it compute today's board.

    See tests/test_rollover.py for required gap scenarios (0, 1, 5, 10+
    days; single and double week-boundary crossings).
    """
    raise NotImplementedError


def derive_color(task, today: date, schedule_context) -> Color:
    """Pure function: task + date + schedule -> current display color."""
    raise NotImplementedError
