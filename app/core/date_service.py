"""
Date-only semantics. Local system date, never timezone-shifted.

This module is the single source of truth for "what day is it" and for
computing week boundaries. Keep it free of business logic (that belongs
in state_engine.py) so it stays trivially testable.
"""

from datetime import date, timedelta
from typing import Optional


def today() -> date:
    return date.today()


def week_start(for_date: date) -> date:
    """Monday of the week containing for_date."""
    return for_date - timedelta(days=for_date.weekday())


def week_end(for_date: date) -> date:
    return week_start(for_date) + timedelta(days=6)


def days_between(start: date, end: date) -> int:
    return (end - start).days


def normalize_due_date(due_date: Optional[date], as_of: Optional[date] = None) -> Optional[date]:
    """A due date in the past is never useful to the scheduler or the
    color rules — clamp it forward to `as_of` (defaults to today) instead
    of silently letting a task sit with a stale, already-elapsed deadline.
    `None` is passed through unchanged (no due date is not the same as a
    past one)."""
    if due_date is None:
        return None
    return max(due_date, as_of if as_of is not None else today())
