"""Pure categorization of tasks into the Today view's sections. No DB or
Qt imports — callers (services/UI) fetch tasks and today's schedule ids,
this just sorts them into buckets.

Bucket precedence (a task lands in exactly one bucket):
    1. completed  — status == COMPLETED
    2. overdue    — has a due_date strictly before today, still active
    3. today      — task_id is in today's schedule
    4. unscheduled — everything else still active (never scheduled, or
                     due later than today)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Set

from app.core.priority_engine import calculate_priority_score
from app.models.task import Task, TaskStatus

_ACTIVE_STATUSES = (TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.DEFERRED)


@dataclass
class TodaySections:
    overdue: List[Task] = field(default_factory=list)
    today: List[Task] = field(default_factory=list)
    unscheduled: List[Task] = field(default_factory=list)
    completed: List[Task] = field(default_factory=list)


def build_today_sections(tasks: List[Task], today: date, scheduled_task_ids: Set[int]) -> TodaySections:
    sections = TodaySections()

    for task in tasks:
        if task.status == TaskStatus.CANCELLED:
            continue
        if task.status == TaskStatus.COMPLETED:
            sections.completed.append(task)
        elif task.status in _ACTIVE_STATUSES and task.due_date is not None and task.due_date < today:
            sections.overdue.append(task)
        elif task.id in scheduled_task_ids:
            sections.today.append(task)
        elif task.status in _ACTIVE_STATUSES:
            sections.unscheduled.append(task)

    for bucket in (sections.overdue, sections.today, sections.unscheduled, sections.completed):
        bucket.sort(key=lambda t: calculate_priority_score(t, today), reverse=True)

    return sections
