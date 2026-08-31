"""
Derives visual color + lifecycle state transitions. Color is NEVER stored
as authoritative state — it is computed from task properties, today's date,
schedule, prior exposure, and completion state (see spec §9).

Also owns midnight/multi-day rollover reconciliation — the single hardest
and most safety-critical piece of this application. Keep it pure (no
datetime.now() calls, no direct DB writes) so it is fully unit-testable;
callers pass in dates and current state, and get back a plan of changes
to apply.

``db_state`` contract (an in-memory snapshot the caller builds from the
repositories and mutates in place; the services layer is responsible for
persisting it back afterwards):

    {
        "tasks": {task_id: Task, ...},
        "schedule": {date: [task_id, ...], ...},   # which tasks were
            expected/scheduled on each date — the sole source of "was this
            task given a reasonable opportunity on this day".
        "weekly_history": [ {"week_start": date, "week_end": date,
                              "completed_task_ids": [...],
                              "missed_task_ids": [...],
                              "deferred_task_ids": [...]}, ... ],
    }

Only the immediately preceding completed week is retained in
``weekly_history`` (spec §22) — reconcile() purges older entries itself
whenever a replayed day closes out a week.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional

from app.config.settings import ORANGE_THRESHOLD, RED_THRESHOLD
from app.core import date_service
from app.models.task import TaskStatus, TaskType


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


def _color_for_missed_count(times_ignored: int) -> Optional[Color]:
    if times_ignored >= RED_THRESHOLD:
        return Color.RED
    if times_ignored >= ORANGE_THRESHOLD:
        return Color.ORANGE
    return None


def _close_out_day(day: date, db_state: dict, tasks_marked_missed: list,
                    state_transitions: list) -> None:
    tasks = db_state["tasks"]
    scheduled_task_ids = db_state["schedule"].get(day, [])

    for task_id in scheduled_task_ids:
        task = tasks.get(task_id)
        if task is None:
            continue

        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            continue

        if task.deferred_at == day:
            # Deliberate defer — never counts as ignored (spec §10, §58).
            task.times_ignored = 0
            continue

        old_color = _color_for_missed_count(task.times_ignored)
        task.times_ignored += 1
        task.days_exposed += 1
        task.last_scheduled_date = day
        task.current_scheduled_date = None
        task.status = TaskStatus.PENDING
        tasks_marked_missed.append(task.id)

        new_color = _color_for_missed_count(task.times_ignored)
        if new_color != old_color:
            state_transitions.append((task.id, old_color, new_color))


def _archive_and_purge_week(sunday: date, db_state: dict) -> Optional[dict]:
    week_start = date_service.week_start(sunday)
    week_end = date_service.week_end(sunday)
    week_dates = [week_start + timedelta(days=i) for i in range(7)]

    tasks = db_state["tasks"]
    completed_ids, missed_ids, deferred_ids = [], [], []
    seen = set()
    for d in week_dates:
        for task_id in db_state["schedule"].get(d, []):
            if task_id in seen:
                continue
            seen.add(task_id)
            task = tasks.get(task_id)
            if task is None:
                continue
            if task.status == TaskStatus.COMPLETED:
                completed_ids.append(task_id)
            elif task.status == TaskStatus.DEFERRED:
                deferred_ids.append(task_id)
            elif task.times_ignored > 0:
                missed_ids.append(task_id)

    entry = {
        "week_start": week_start,
        "week_end": week_end,
        "completed_task_ids": completed_ids,
        "missed_task_ids": missed_ids,
        "deferred_task_ids": deferred_ids,
    }

    history = db_state.setdefault("weekly_history", [])
    history.append(entry)
    # One-week rolling history (spec §22-23): keep only the most recently
    # completed week, purge anything older.
    db_state["weekly_history"] = [
        h for h in history if h["week_start"] >= week_start
    ]
    return entry


def _compute_today_board(today: date, db_state: dict) -> list:
    tasks = db_state["tasks"]
    board = []
    for task_id in db_state["schedule"].get(today, []):
        task = tasks.get(task_id)
        if task is None:
            continue
        context = {"expected_date": task.current_scheduled_date or task.due_date}
        board.append({"task_id": task_id, "color": derive_color(task, today, context)})
    return board


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
    reconciled_dates: List[date] = []
    tasks_marked_missed: list = []
    state_transitions: list = []
    weeks_archived: list = []

    if last_known_date is not None:
        # last_known_date is the day whose board was last computed, but it
        # may never have been closed out itself (app closed before its own
        # midnight rollover ran) — so replay starts there, not the day
        # after, and runs up to (excluding) today.
        current_date = last_known_date
        while current_date < today:
            reconciled_dates.append(current_date)
            _close_out_day(current_date, db_state, tasks_marked_missed, state_transitions)

            if current_date == date_service.week_end(current_date):
                archived = _archive_and_purge_week(current_date, db_state)
                if archived is not None:
                    weeks_archived.append(archived)

            current_date += timedelta(days=1)

    new_today_board = _compute_today_board(today, db_state)

    return ReconciliationResult(
        reconciled_dates=reconciled_dates,
        tasks_marked_missed=tasks_marked_missed,
        state_transitions=state_transitions,
        weeks_archived=weeks_archived,
        new_today_board=new_today_board,
    )


def derive_project_color() -> Color:
    """Projects are always PURPLE, regardless of any child task's state —
    a missed/red child is that child's problem, never the project's own
    color (spec §41)."""
    return Color.PURPLE


def derive_color(task, today: date, schedule_context) -> Optional[Color]:
    """
    Pure function: task + date + schedule -> current display color, or
    None when no special color applies (e.g. an on-time completion, or a
    future task not yet relevant — spec §40 explicitly allows a neutral,
    non-green appearance for ordinary completions; v1 represents that
    neutral state as None rather than inventing a 7th color).
    """
    if task.task_type == TaskType.FIXED_EVENT:
        return Color.BLUE

    if task.status == TaskStatus.CANCELLED:
        return None

    expected_date = None
    if schedule_context:
        expected_date = schedule_context.get("expected_date")

    if task.status == TaskStatus.COMPLETED:
        if task.completed_at is not None and expected_date is not None \
                and task.completed_at < expected_date:
            return Color.GREEN
        return None

    if task.status == TaskStatus.DEFERRED:
        return None

    missed_color = _color_for_missed_count(task.times_ignored)
    if missed_color is not None:
        return missed_color

    if today == task.due_date or today == expected_date:
        return Color.YELLOW

    return None
