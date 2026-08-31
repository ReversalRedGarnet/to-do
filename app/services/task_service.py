"""Business logic for creating/editing/completing/deferring tasks.
UI widgets must call into this layer, never touch repositories directly."""

from datetime import date
from typing import Optional

from app.config.settings import DEFAULT_TASK_VALUES
from app.core import date_service
from app.models.task import Task, TaskStatus, TaskType

_ACTIVE_STATUSES = (TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.DEFERRED)


def _iso_week(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


class TaskService:
    def __init__(self, task_repository, notification_service):
        self._tasks = task_repository
        self._notifications = notification_service

    def create_task(
        self,
        title: str,
        *,
        description: str = "",
        task_type: TaskType = TaskType.NORMAL,
        project_id: Optional[int] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
        urgency: Optional[int] = None,
        seriousness: Optional[int] = None,
        effort: Optional[int] = None,
        available_from: Optional[date] = None,
        due_date: Optional[date] = None,
        recurrence_rule_id: Optional[int] = None,
    ) -> Task:
        """Sensible defaults per spec §25 — the user only edits what matters."""
        today = date_service.today()
        task = Task(
            id=None,
            title=title,
            description=description,
            task_type=task_type,
            project_id=project_id,
            category=category or DEFAULT_TASK_VALUES["category"],
            importance=importance if importance is not None else DEFAULT_TASK_VALUES["importance"],
            urgency=urgency if urgency is not None else DEFAULT_TASK_VALUES["urgency"],
            seriousness=seriousness if seriousness is not None else DEFAULT_TASK_VALUES["seriousness"],
            effort=effort if effort is not None else DEFAULT_TASK_VALUES["effort"],
            available_from=available_from if available_from is not None else today,
            due_date=due_date,
            status=TaskStatus.PENDING,
            created_at=today,
            recurrence_rule_id=recurrence_rule_id,
            created_week=_iso_week(today),
        )
        task.id = self._tasks.create(task)
        return task

    def get_task(self, task_id: int) -> Optional[Task]:
        return self._tasks.get_by_id(task_id)

    def complete_task(self, task_id: int, completed_on: Optional[date] = None) -> Task:
        task = self._tasks.get_by_id(task_id)
        task.status = TaskStatus.COMPLETED
        task.completed_at = completed_on or date_service.today()
        task.progress = 100
        self._tasks.update(task)
        return task

    def defer_task(self, task_id: int, defer_to_date: date, today: Optional[date] = None) -> Task:
        """Records a deliberate defer (spec §10) — must never be conflated
        with an ignored/missed task. Does not touch task_schedule directly;
        callers pair this with services.schedule_service to move the
        persisted schedule row."""
        task = self._tasks.get_by_id(task_id)
        task.status = TaskStatus.SCHEDULED
        task.deferred_at = today or date_service.today()
        task.current_scheduled_date = defer_to_date
        task.times_deferred += 1
        self._tasks.update(task)
        return task

    def move_task(self, task_id: int, new_date: date) -> Task:
        """Manual override of the scheduled date (spec §29 "Move to
        another day") — distinct from Defer: no deferred_at bookkeeping,
        since this isn't "I chose not to do this today", just a
        relocation. Callers pair this with schedule_service to move the
        persisted schedule row."""
        task = self._tasks.get_by_id(task_id)
        task.current_scheduled_date = new_date
        self._tasks.update(task)
        return task

    def update_task(self, task_id: int, **fields) -> Task:
        """Full-field edit (spec §28/§29 "Edit"). Only overwrites fields
        explicitly passed; safe to call with a partial set."""
        task = self._tasks.get_by_id(task_id)
        for key, value in fields.items():
            setattr(task, key, value)
        self._tasks.update(task)
        return task

    def cancel_task(self, task_id: int) -> Task:
        task = self._tasks.get_by_id(task_id)
        task.status = TaskStatus.CANCELLED
        self._tasks.update(task)
        return task

    def project_progress(self, project_id: int) -> int:
        """0-100, computed from child tasks — never stored on Project
        directly (spec §41; see models/project.py)."""
        children = self._tasks.list_by_project(project_id)
        if not children:
            return 0
        completed = sum(1 for t in children if t.status == TaskStatus.COMPLETED)
        return round(100 * completed / len(children))

    def next_actionable_item(self, project_id: int) -> Optional[Task]:
        """The project's next child task worth surfacing — earliest due
        date first, undated tasks last. A missed child stays the
        project's problem to surface, not the project's own color
        (spec §41: the project never ages into orange/red itself)."""
        candidates = [
            t for t in self._tasks.list_by_project(project_id)
            if t.status in _ACTIVE_STATUSES
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda t: (t.due_date is None, t.due_date, t.id))
