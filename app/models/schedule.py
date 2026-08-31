"""Weekly schedule / task_schedule row domain model."""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class ScheduleEntry:
    id: Optional[int]
    task_id: int
    week_start: date
    scheduled_date: date
    schedule_reason: str  # see core/scheduling_engine.py reason constants
    manual_override: bool = False
    locked: bool = False
