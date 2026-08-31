"""Recurrence rule domain model. Mirrors the `recurrence_rules` table.

Recurring definitions persist indefinitely (spec §44); each occurrence is
generated as its own Task row via services/recurrence_service.py — past
occurrences are not retained as permanent history."""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import List, Optional


class RecurrenceFrequency(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM_WEEKDAYS = "custom_weekdays"


@dataclass
class RecurrenceRule:
    id: Optional[int]
    frequency: RecurrenceFrequency
    interval: int = 1
    weekdays: Optional[List[int]] = None  # 0=Monday..6=Sunday, only for CUSTOM_WEEKDAYS
    created_at: Optional[date] = None
