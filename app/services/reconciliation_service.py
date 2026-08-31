"""
Wraps core.state_engine.reconcile against real repositories — the same
pass runs at app startup (main.py) and from the mid-session rollover
timer (ui/main_window.py) whenever the running app detects midnight has
passed (spec §19). Kept in one place so both callers replay/persist
identically.
"""

from datetime import date

from app.core.state_engine import ReconciliationResult, reconcile


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

        for task in all_tasks.values():
            self._tasks.update(task)
        if result.weeks_archived:
            self._history_service.apply_reconciliation_archives(result.weeks_archived)

        self._app_state.set_last_known_date(today)
        return result
