"""Owns the one-week rolling history retention policy (spec §22-23)."""

from datetime import date


class HistoryService:
    def __init__(self, history_repository):
        self._history = history_repository

    def archive_week(self, week_start: date, week_end: date, snapshot: dict) -> None:
        self._history.archive(week_start, week_end, snapshot)
        self.purge_older_than_previous_week(week_start)

    def purge_older_than_previous_week(self, current_week_start: date) -> None:
        """Only the immediately preceding completed week is retained —
        everything older is purged the moment a new week is archived."""
        self._history.purge_older_than(current_week_start)

    def apply_reconciliation_archives(self, weeks_archived: list) -> None:
        """Persists the weeks_archived entries produced by
        core.state_engine.reconcile (see main.py startup sequence)."""
        for entry in weeks_archived:
            self.archive_week(
                entry["week_start"],
                entry["week_end"],
                {
                    "completed_task_ids": entry["completed_task_ids"],
                    "missed_task_ids": entry["missed_task_ids"],
                    "deferred_task_ids": entry["deferred_task_ids"],
                },
            )
