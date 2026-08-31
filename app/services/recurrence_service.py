"""Turns a completed recurring task's occurrence into the next one (spec
§44). The just-completed Task row is never touched here — it keeps its
own id and COMPLETED status so today's/history's board still shows it
correctly; this only ever INSERTs a new Task row for the next occurrence."""

from datetime import date
from typing import Optional

from app.core import date_service
from app.core.recurrence_engine import generate_next_occurrence
from app.models.recurrence import RecurrenceFrequency, RecurrenceRule
from app.models.task import Task, TaskStatus


def _iso_week(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


class RecurrenceService:
    def __init__(self, task_repository, recurrence_repository):
        self._tasks = task_repository
        self._recurrence_rules = recurrence_repository

    def set_recurrence(
        self, task_id: int, frequency: RecurrenceFrequency,
        interval: int = 1, weekdays: Optional[list] = None,
    ) -> None:
        """Creates the RecurrenceRule row and links it to the task — called
        from the task editor (spec: recurrence must be usable through the
        app itself, not just seed data)."""
        rule = RecurrenceRule(
            id=None, frequency=frequency, interval=interval, weekdays=weekdays,
            created_at=date_service.today(),
        )
        rule_id = self._recurrence_rules.create(rule)
        task = self._tasks.get_by_id(task_id)
        task.recurrence_rule_id = rule_id
        self._tasks.update(task)

    def get_rule_for_task(self, task: Task) -> Optional[RecurrenceRule]:
        if task.recurrence_rule_id is None:
            return None
        return self._recurrence_rules.get_by_id(task.recurrence_rule_id)

    def clear_recurrence(self, task_id: int) -> None:
        task = self._tasks.get_by_id(task_id)
        task.recurrence_rule_id = None
        self._tasks.update(task)

    def ensure_next_occurrence(self, completed_task: Task) -> Optional[Task]:
        """Called after a recurring task is marked complete. Returns the
        newly created occurrence, or None if the task isn't recurring or
        its rule no longer exists."""
        if completed_task.recurrence_rule_id is None:
            return None
        rule = self._recurrence_rules.get_by_id(completed_task.recurrence_rule_id)
        if rule is None:
            return None

        anchor = completed_task.due_date or completed_task.available_from or date_service.today()
        next_anchor = generate_next_occurrence(rule, anchor)
        shift = next_anchor - anchor

        new_due = completed_task.due_date + shift if completed_task.due_date else None
        new_available = (
            completed_task.available_from + shift if completed_task.available_from else next_anchor
        )

        today = date_service.today()
        new_task = Task(
            id=None,
            title=completed_task.title,
            description=completed_task.description,
            task_type=completed_task.task_type,
            project_id=completed_task.project_id,
            category=completed_task.category,
            importance=completed_task.importance,
            urgency=completed_task.urgency,
            seriousness=completed_task.seriousness,
            effort=completed_task.effort,
            available_from=new_available,
            due_date=new_due,
            status=TaskStatus.PENDING,
            created_at=today,
            recurrence_rule_id=completed_task.recurrence_rule_id,
            created_week=_iso_week(today),
        )
        new_task.id = self._tasks.create(new_task)
        return new_task
