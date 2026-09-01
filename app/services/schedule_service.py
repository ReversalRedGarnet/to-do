"""Orchestrates core.scheduling_engine against real repositories."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from app.config.settings import Capacity, DEFAULT_WEEKLY_CAPACITY, UTILIZATION_TARGET
from app.core import date_service
from app.core.priority_engine import calculate_priority_score, priority_label
from app.core.scheduling_engine import diff_week_plan, generate_weekly_schedule
from app.models.schedule import ScheduleEntry
from app.models.task import TaskStatus

_AGGRESSIVENESS_UTILIZATION_TARGET = {
    "relaxed": 0.60,
    "standard": UTILIZATION_TARGET,
    "aggressive": 0.90,
}


@dataclass
class WeekPlan:
    """A proposed (not-yet-persisted) result of the greedy allocator for
    one week — what `ScheduleService.preview_week` computes and what
    `apply_plan` later commits. `changes` is the diff the preview UI
    renders; `protected_task_ids` are tasks the plan deliberately left
    untouched (locked or manually-placed) and must never be included when
    persisting."""
    week_start: date
    schedule: dict
    changes: list
    protected_task_ids: Set[int] = field(default_factory=set)


@dataclass
class WeekPlanSnapshot:
    """Everything `undo_plan` needs to restore a week to how it looked
    immediately before `apply_plan` ran — the week's prior `task_schedule`
    rows plus the prior status/current_scheduled_date/last_scheduled_date
    of every task `apply_plan` is about to touch."""
    week_start: date
    entries: List[ScheduleEntry]
    task_fields: Dict[int, dict]


class ScheduleService:
    def __init__(self, task_repository, schedule_repository, fixed_event_repository,
                 settings_repository=None):
        self._tasks = task_repository
        self._schedules = schedule_repository
        self._fixed_events = fixed_event_repository
        self._settings = settings_repository

    def _default_capacities(self) -> list:
        """User-configured daily capacities (Settings screen, spec §47) when
        available, falling back to the v1 constant otherwise — e.g. in
        tests/callers that don't wire a settings_repository."""
        if self._settings is None:
            return DEFAULT_WEEKLY_CAPACITY
        try:
            names = self._settings.get().daily_capacities
            return [Capacity[name] for name in names]
        except (KeyError, TypeError, ValueError):
            return DEFAULT_WEEKLY_CAPACITY

    def capacity_for_day(self, day: date) -> Capacity:
        """The configured capacity for a single date's weekday, honoring
        Settings the same way `_default_capacities()` does — used by the
        Today header's planned-load summary and the Week view's per-day
        load indicator."""
        capacities = self._default_capacities()
        return capacities[day.weekday()]

    def _week_gen_settings(self) -> tuple:
        """(weekend_allowed, allow_low_priority_automove, utilization_target)
        from Settings (Phase 6), falling back to v1 defaults when no
        settings_repository is wired — same pattern as
        `_default_capacities()`."""
        if self._settings is None:
            return True, True, UTILIZATION_TARGET
        try:
            settings = self._settings.get()
            target = _AGGRESSIVENESS_UTILIZATION_TARGET.get(
                settings.week_gen_aggressiveness, UTILIZATION_TARGET
            )
            return settings.week_gen_weekend_allowed, settings.week_gen_allow_low_priority_automove, target
        except (AttributeError, TypeError):
            return True, True, UTILIZATION_TARGET

    def preview_week(self, week_start: date, *, capacities: Optional[list] = None,
                      weekend_allowed: Optional[bool] = None,
                      aggressiveness: Optional[str] = None) -> WeekPlan:
        """Computes what Generate Week *would* do without persisting
        anything — the read-only half of the old `generate_week`. Tasks
        with an existing `locked=1` or `manual_override=1` schedule row
        this week are excluded from re-placement and instead injected back
        at their existing date (like a fixed event), so a rerun can never
        silently move a task the user placed on purpose. When
        `week_gen_allow_low_priority_automove` is off (Settings), an
        already-placed, non-locked task scored "Low" is protected the same
        way for this run — new/never-placed low-priority work is still
        freely placed."""
        week_end = week_start + timedelta(days=6)
        settings_weekend_allowed, settings_allow_automove, settings_target = self._week_gen_settings()
        capacities = capacities if capacities is not None else self._default_capacities()
        weekend_allowed = settings_weekend_allowed if weekend_allowed is None else weekend_allowed
        utilization_target = (
            _AGGRESSIVENESS_UTILIZATION_TARGET.get(aggressiveness, UTILIZATION_TARGET)
            if aggressiveness is not None else settings_target
        )

        existing_entries = self._schedules.get_week(week_start)
        protected_entries = [e for e in existing_entries if e.locked or e.manual_override]

        if not settings_allow_automove:
            already_locked_ids = {e.task_id for e in protected_entries}
            for entry in existing_entries:
                if entry.task_id in already_locked_ids:
                    continue
                task = self._tasks.get_by_id(entry.task_id)
                if task is None:
                    continue
                score = calculate_priority_score(task, week_start)
                if priority_label(score) == "Low":
                    protected_entries.append(entry)

        protected_task_ids = {e.task_id for e in protected_entries}

        tasks = [
            t for t in self._tasks.list_eligible_for_week(week_start, week_end)
            if t.id not in protected_task_ids
        ]
        fixed_events = self._fixed_events.list_between(week_start, week_end)

        locked_placements = []
        for entry in protected_entries:
            task = self._tasks.get_by_id(entry.task_id)
            if task is not None:
                locked_placements.append((task, entry.scheduled_date))

        schedule = generate_weekly_schedule(
            tasks, fixed_events, week_start, capacities,
            locked_placements=locked_placements, weekend_allowed=weekend_allowed,
            utilization_target=utilization_target,
        )
        changes = diff_week_plan(existing_entries, schedule)

        return WeekPlan(week_start=week_start, schedule=schedule, changes=changes,
                         protected_task_ids=protected_task_ids)

    def apply_plan(self, plan: WeekPlan) -> WeekPlanSnapshot:
        """Persists a previously computed `WeekPlan` — snapshotting the
        week's prior state first so the UI can offer a one-shot Undo.
        Protected (locked/manual_override) tasks are never included in the
        rows written here; `ScheduleRepository.replace_week` also leaves
        their existing rows alone even if it were passed one by mistake."""
        week_start = plan.week_start
        snapshot_entries = self._schedules.get_week(week_start)

        new_task_ids = {
            p.task_id for placements in plan.schedule.values()
            for p in placements if p.task_id is not None
        }
        touched_task_ids = {e.task_id for e in snapshot_entries} | new_task_ids
        task_fields = {}
        for task_id in touched_task_ids:
            task = self._tasks.get_by_id(task_id)
            if task is not None:
                task_fields[task_id] = dict(
                    status=task.status,
                    current_scheduled_date=task.current_scheduled_date,
                    last_scheduled_date=task.last_scheduled_date,
                )
        snapshot = WeekPlanSnapshot(week_start=week_start, entries=snapshot_entries, task_fields=task_fields)

        entries = [
            ScheduleEntry(
                id=None,
                task_id=placement.task_id,
                week_start=week_start,
                scheduled_date=placement.date,
                schedule_reason=placement.reason,
            )
            for placements in plan.schedule.values()
            for placement in placements
            if placement.task_id is not None and placement.task_id not in plan.protected_task_ids
        ]
        # A protected task that is neither locked nor manually overridden
        # (e.g. the "low-priority auto-move disabled" case) has no special
        # protection at the repository level — replace_week's blanket
        # delete would otherwise remove its row since we deliberately left
        # it out of `entries` above. Re-add its existing row unchanged so
        # it survives the delete-then-insert instead of vanishing.
        already_covered = {e.task_id for e in entries} | {
            e.task_id for e in snapshot_entries if e.locked or e.manual_override
        }
        for entry in snapshot_entries:
            if entry.task_id in plan.protected_task_ids and entry.task_id not in already_covered:
                entries.append(entry)
                already_covered.add(entry.task_id)
        self._schedules.replace_week(week_start, entries)

        for entry in entries:
            task = self._tasks.get_by_id(entry.task_id)
            task.status = TaskStatus.SCHEDULED
            task.current_scheduled_date = entry.scheduled_date
            task.last_scheduled_date = entry.scheduled_date
            self._tasks.update(task)

        return snapshot

    def undo_plan(self, snapshot: WeekPlanSnapshot) -> None:
        """Restores a week to exactly how it looked before the matching
        `apply_plan` call — single-level, session-only (the snapshot lives
        only in the caller's memory, matching the app's existing explicit-
        action model rather than a persisted undo log)."""
        self._schedules.replace_week(snapshot.week_start, snapshot.entries)
        for task_id, fields in snapshot.task_fields.items():
            task = self._tasks.get_by_id(task_id)
            if task is None:
                continue
            task.status = fields["status"]
            task.current_scheduled_date = fields["current_scheduled_date"]
            task.last_scheduled_date = fields["last_scheduled_date"]
            self._tasks.update(task)

    def generate_week(self, week_start: date, capacities: Optional[list] = None) -> dict:
        """Runs the greedy allocator for this week and persists the result
        immediately — kept for existing/simple callers (reconciliation,
        scripts) that don't need the preview/undo flow. Equivalent to
        `preview_week` followed by `apply_plan`. Fixed-date events are
        read-only inputs (spec §5.3) — never rewritten."""
        plan = self.preview_week(week_start, capacities=capacities)
        self.apply_plan(plan)
        return plan.schedule

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

    def schedule_task_to_day(self, task_id: int, week_start: date, new_date: date) -> None:
        """Drag-and-drop onto a day (Phase 4) — unlike `move_task`, works
        even when the task has no existing row this week (e.g. dragged in
        from an "Unscheduled" list), via `upsert_task_day`. Always records
        it as a manual placement so a later Generate Week never silently
        relocates it."""
        self._schedules.upsert_task_day(task_id, week_start, new_date, reason="USER_SELECTED")

    def unschedule_task(self, task_id: int, week_start: date) -> None:
        """Drag-and-drop onto "Unscheduled" (Phase 4) — removes the
        task_schedule row entirely; callers pair this with
        TaskService to reset the task back to PENDING."""
        self._schedules.delete_task_from_week(task_id, week_start)

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
