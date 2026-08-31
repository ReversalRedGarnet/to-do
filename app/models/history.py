"""Weekly history domain model — only the immediately previous week is kept."""

from dataclasses import dataclass
from datetime import date


@dataclass
class WeeklyHistoryEntry:
    id: int
    week_start: date
    week_end: date
    # Snapshot of what happened: completed / missed / deferred task ids.
    # Purged once it is no longer the "previous" week — see services/history_service.py.
