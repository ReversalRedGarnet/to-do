"""Orchestrates core.scheduling_engine against real repositories."""

from datetime import date, timedelta
from typing import List, Optional

from app.config.settings import DEFAULT_WEEKLY_CAPACITY
from app.core import date_service
from app.core.scheduling_engine import generate_weekly_schedule
from app.models.schedule import ScheduleEntry
from app.models.task import TaskStatus


class ScheduleService:
    def __init__(self, task_repository, schedule_repository, fixed_event_repository):
        self._tasks = task_repository
        self._schedules = schedule_repository
        self._fixed_events = fixed_event_repository

    def generate_week(self, week_start: date, capacities: Optional[list] = None) -> dict:
        """Runs the greedy allocator for this week and persists the result.
        Fixed-date events are read-only inputs (spec §5.3) — never rewritten."""
        week_end = week_start + timedelta(days=6)
        capacities = capacities if capacities is not None else DEFAULT_WEEKLY_CAPACITY

        tasks = self._tasks.list_eligible_for_week(week_start, week_end)
        fixed_events = self._fixed_events.list_between(week_start, week_end)

        schedule = generate_weekly_schedule(tasks, fixed_events, week_start, capacities)

        entries = [
            ScheduleEntry(
                id=None,
                task_id=placement.task_id,
                week_start=week_start,
                scheduled_date=placement.date,
                schedule_reason=placement.reason,
            )
            for placements in schedule.values()
            for placement in placements
            if placement.task_id is not None
        ]
        self._schedules.replace_week(week_start, entries)

        for entry in entries:
            task = self._tasks.get_by_id(entry.task_id)
            task.status = TaskStatus.SCHEDULED
            task.current_scheduled_date = entry.scheduled_date
            task.last_scheduled_date = entry.scheduled_date
            self._tasks.update(task)

        return schedule

    def get_week(self, week_start: date) -> dict:
        return self._schedules.get_week_by_day(week_start)

    def week_is_planned(self, week_start: date) -> bool:
        return self._schedules.week_exists(week_start)

    def regenerate_after_change(self, week_start: date, capacities: Optional[list] = None) -> dict:
        """Recompute the week's schedule after tasks change (added, edited,
        missed) — same allocator, re-run from scratch (v1 has no
        incremental patching, consistent with "no backtracking" scope)."""
        return self.generate_week(week_start, capacities)

    def move_task(self, task_id: int, week_start: date, new_date: date) -> None:
        self._schedules.move_task(task_id, week_start, new_date)

    def lock_task(self, task_id: int, week_start: date, locked: bool = True) -> None:
        self._schedules.set_locked(task_id, week_start, locked)

    def get_fixed_events_between(self, start: date, end: date) -> list:
        return self._fixed_events.list_between(start, end)

    def get_task_ids_between(self, start_date: date, end_date: date) -> dict:
        """date -> [task_id, ...] for every day in [start_date, end_date),
        spanning as many weeks as needed. Used by the startup reconciliation
        pass (see main.py) to build state_engine.reconcile's db_state."""
        by_day: dict = {}
        week_cursor = date_service.week_start(start_date)
        last_week = date_service.week_start(end_date - timedelta(days=1)) if end_date > start_date else week_cursor
        while week_cursor <= last_week:
            for day, entries in self._schedules.get_week_by_day(week_cursor).items():
                if start_date <= day < end_date:
                    by_day[day] = [e.task_id for e in entries]
            week_cursor += timedelta(days=7)
        return by_day
