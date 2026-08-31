"""
Date-only semantics. Local system date, never timezone-shifted.

This module is the single source of truth for "what day is it" and for
computing week boundaries. Keep it free of business logic (that belongs
in state_engine.py) so it stays trivially testable.
"""

from datetime import date, timedelta


def today() -> date:
    return date.today()


def week_start(for_date: date) -> date:
    """Monday of the week containing for_date."""
    return for_date - timedelta(days=for_date.weekday())


def week_end(for_date: date) -> date:
    return week_start(for_date) + timedelta(days=6)


def days_between(start: date, end: date) -> int:
    return (end - start).days
