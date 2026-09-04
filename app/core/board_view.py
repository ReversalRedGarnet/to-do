"""Pure categorization of tasks into the Today view's sections. No DB or
Qt imports — callers (services/UI) fetch tasks, this just sorts them into
due-date buckets using core/date_service.py for all date-boundary math.

Bucket precedence (a task lands in exactly one bucket):
    1. completed             — status == COMPLETED
    2. overdue               — due_date < today, still active
    3. today                 — due_date == today
    4. tomorrow               — due_date == today + 1 day
    5. this_week              — due_date after tomorrow, through the end
                                 of the current calendar week
    6. this_month             — due_date after the end of this week,
                                 through the last day of the current
                                 calendar month
    7. next_month_or_later    — due_date on or after the 1st of next month
    8. unscheduled            — no due_date at all
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List

from app.core import date_service
from app.core.priority_engine import calculate_priority_score
from app.models.task import Task, TaskStatus

_ACTIVE_STATUSES = (TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.DEFERRED)


@dataclass
class TodaySections:
    overdue: List[Task] = field(default_factory=list)
    today: List[Task] = field(default_factory=list)
    tomorrow: List[Task] = field(default_factory=list)
    this_week: List[Task] = field(default_factory=list)
    this_month: List[Task] = field(default_factory=list)
    next_month_or_later: List[Task] = field(default_factory=list)
    unscheduled: List[Task] = field(default_factory=list)
    completed: List[Task] = field(default_factory=list)


def build_today_sections(tasks: List[Task], today: date) -> TodaySections:
    sections = TodaySections()

    tomorrow = today + timedelta(days=1)
    week_end = date_service.week_end(today)
    month_end = date_service.month_end(today)

    for task in tasks:
        if task.status == TaskStatus.CANCELLED:
            continue
        if task.status == TaskStatus.COMPLETED:
            sections.completed.append(task)
        elif task.status not in _ACTIVE_STATUSES:
            continue
        elif task.due_date is None:
            sections.unscheduled.append(task)
        elif task.due_date < today:
            sections.overdue.append(task)
        elif task.due_date == today:
            sections.today.append(task)
        elif task.due_date == tomorrow:
            sections.tomorrow.append(task)
        elif task.due_date <= week_end:
            sections.this_week.append(task)
        elif task.due_date <= month_end:
            sections.this_month.append(task)
        else:
            sections.next_month_or_later.append(task)

    for bucket in (
        sections.overdue, sections.today, sections.tomorrow, sections.this_week,
        sections.this_month, sections.next_month_or_later, sections.unscheduled,
        sections.completed,
    ):
        bucket.sort(key=lambda t: calculate_priority_score(t, today), reverse=True)

    return sections
