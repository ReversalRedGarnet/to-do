"""
Wraps core.state_engine.reconcile against real repositories — the same
pass runs at app startup (main.py) and from the mid-session rollover
timer (ui/main_window.py) whenever the running app detects midnight has
passed (spec §19). Kept in one place so both callers replay/persist
identically.
"""

import logging
from datetime import date

from app.core import date_service
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

        self._repair_schedule_drift(all_tasks)

        for task in all_tasks.values():
            self._tasks.update(task)
        if result.weeks_archived:
            self._history_service.apply_reconciliation_archives(result.weeks_archived)

        self._app_state.set_last_known_date(today)
        return result

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
