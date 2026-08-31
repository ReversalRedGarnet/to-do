"""Fixed/scheduled event (BLUE) domain model. Mirrors the `fixed_events` table.

Distinct from Task even though TaskType.FIXED_EVENT exists as an enum
member — the scheduling engine takes fixed events as a separate input
(see core/scheduling_engine.generate_weekly_schedule) because they are
never moved and never enter priority scoring; they only consume capacity."""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class FixedEvent:
    id: Optional[int]
    title: str
    description: str
    event_date: date
    event_time: Optional[str] = None  # informational only, e.g. "15:00"
    category: Optional[str] = None
    capacity_cost: int = 0
