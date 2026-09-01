"""
Wraps core.state_engine.reconcile against real repositories — the same
pass runs at app startup (main.py) and from the mid-session rollover
timer (ui/main_window.py) whenever the running app detects midnight has
passed (spec §19). Kept in one place so both callers replay/persist
identically.
"""

import logging
from datetime import date, timedelta

from app.config.settings import EFFORT_UNITS
from app.core import date_service
from app.core.scheduling_engine import FIXED_EVENT, Placement, rebalance_after_missed_task
from app.core.state_engine import ReconciliationResult, reconcile
from app.models.task import TaskStatus

logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(self, task_repository, schedule_service, app_state_repository, history_service):
        self._tasks = task_repository
        self._schedule_service = schedule_service
        self._app_state = app_state_repository
        self._history_service = history_service

    def run(self, today: date) -> ReconciliationResult:
        """Replays every day from the last confirmed date up to (excluding)
        `today`, persists the resulting task/history changes, and only then
        advances `last_known_date` — never speculatively (see
        core.state_engine.reconcile's docstring)."""
        last_known_date = self._app_state.get_last_known_date()
        schedule_map = (
            self._schedule_service.get_task_ids_between(last_known_date, today)
            if last_known_date is not None else {}
        )
        all_tasks = {t.id: t for t in self._tasks.list_all(include_cancelled=True)}
        db_state = {"tasks": all_tasks, "schedule": schedule_map, "weekly_history": []}

        result = reconcile(last_known_date, today, db_state)

        for task_id in result.tasks_marked_missed:
            task = all_tasks.get(task_id)
            if task is not None:
                self._attempt_rebalance(task, today, all_tasks)

        self._repair_schedule_drift(all_tasks)

        for task in all_tasks.values():
            self._tasks.update(task)
        if result.weeks_archived:
            self._history_service.apply_reconciliation_archives(result.weeks_archived)

        self._app_state.set_last_known_date(today)
        return result

    def _attempt_rebalance(self, missed_task, today: date, all_tasks: dict) -> None:
        """Targeted single-swap recovery (spec: a missed task must not
        just pile onto the busiest remaining day) — runs immediately when
        `reconcile()` detects a task was missed, instead of leaving it
        PENDING/unscheduled until the next full Generate Week re-plan
        (which stays available unchanged as the fallback for anything
        this doesn't handle — e.g. a multi-week gap, see the `today >
        week_end_date` guard below). core.scheduling_engine.
        rebalance_after_missed_task itself stays pure; this method is
        purely the DB-facing plumbing around it."""
        missed_day = missed_task.last_scheduled_date
        if missed_day is None:
            return
        week_start = date_service.week_start(missed_day)
        week_end_date = date_service.week_end(missed_day)
        if today > week_end_date:
            return  # that week is already fully behind us

        remaining_days = [today + timedelta(days=i) for i in range((week_end_date - today).days + 1)]
        remaining_state = {d: [] for d in remaining_days}

        for day_entries in self._schedule_service.get_week(week_start).values():
            for entry in day_entries:
                if entry.scheduled_date not in remaining_state or entry.task_id == missed_task.id:
                    continue
                placed_task = all_tasks.get(entry.task_id)
                if placed_task is None:
                    continue
                remaining_state[entry.scheduled_date].append(Placement(
                    date=entry.scheduled_date, reason=entry.schedule_reason,
                    capacity_used=EFFORT_UNITS[placed_task.effort], task_id=entry.task_id,
                ))
        for event in self._schedule_service.get_fixed_events_between(today, week_end_date):
            if event.event_date in remaining_state:
                remaining_state[event.event_date].append(Placement(
                    date=event.event_date, reason=FIXED_EVENT,
                    capacity_used=event.capacity_cost, fixed_event_id=event.id,
                ))

        before = {(day, id(p)) for day, placements in remaining_state.items() for p in placements}
        rebalance_after_missed_task(missed_task, remaining_state)
        placement_by_key = {
            (day, id(p)): p for day, placements in remaining_state.items() for p in placements
        }
        changed_keys = set(placement_by_key) - before

        for day, _pid in changed_keys:
            placement = placement_by_key[(day, _pid)]
            if placement.task_id is None:
                continue
            self._schedule_service.apply_rebalance_placement(placement.task_id, week_start, day, placement.reason)
            placed_task = all_tasks.get(placement.task_id)
            if placed_task is not None:
                placed_task.status = TaskStatus.SCHEDULED
                placed_task.current_scheduled_date = day
                placed_task.last_scheduled_date = day

    def _repair_schedule_drift(self, all_tasks: dict) -> None:
        """Data-integrity guard (spec §52 "corrupted/missing weekly
        schedule"): ScheduleService.generate_week persists task_schedule
        rows and then updates each task's status/current_scheduled_date
        in separate commits — a crash between those two steps could leave
        a task marked SCHEDULED with no matching task_schedule row. Any
        such task is reset to PENDING so the next Generate Week picks it
        back up, instead of silently stranding it off the board forever."""
        for task in all_tasks.values():
            if task.status != TaskStatus.SCHEDULED or task.current_scheduled_date is None:
                continue
            week = date_service.week_start(task.current_scheduled_date)
            day_entries = self._schedule_service.get_week(week).get(task.current_scheduled_date, [])
            if not any(entry.task_id == task.id for entry in day_entries):
                logger.warning(
                    "Task %s marked SCHEDULED for %s with no matching schedule row — resetting to PENDING",
                    task.id, task.current_scheduled_date,
                )
                task.status = TaskStatus.PENDING
                task.current_scheduled_date = None
