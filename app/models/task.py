"""Task domain model. Mirrors the `tasks` table — see database/schema.py."""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class TaskType(Enum):
    NORMAL = "normal"
    PROJECT_CHILD = "project_child"
    FIXED_EVENT = "fixed_event"
    RECURRING = "recurring"


class TaskStatus(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: Optional[int]
    title: str
    description: str
    task_type: TaskType
    project_id: Optional[int]
    category: str

    importance: int   # 1-5
    urgency: int      # 1-5
    seriousness: int  # 1-5
    effort: int       # 1-5

    due_date: Optional[date]

    status: TaskStatus
    progress: int = 0  # 0-100, optional

    created_at: Optional[date] = None
    completed_at: Optional[date] = None
    deferred_at: Optional[date] = None

    last_scheduled_date: Optional[date] = None
    current_scheduled_date: Optional[date] = None

    days_exposed: int = 0
    times_deferred: int = 0
    times_ignored: int = 0

    recurrence_rule_id: Optional[int] = None
    created_week: Optional[str] = None  # ISO week string, e.g. "2026-W36"

    # NOTE: color is intentionally NOT a field here.
    # It is derived by core/state_engine.py from task properties + today's
    # date + schedule + completion state. Never persist color directly.
