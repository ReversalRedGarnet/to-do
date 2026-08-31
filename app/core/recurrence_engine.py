"""
Generates schedulable occurrences from recurrence_rules. Past occurrences
are not retained as permanent history (spec §44).

Kept pure and testable (no DB, no datetime.now()) — callers pass in
`after_date` explicitly, same convention as core.priority_engine and
core.scheduling_engine.
"""

import calendar
from datetime import date, timedelta

from app.models.recurrence import RecurrenceFrequency


def _add_months(d: date, months: int) -> date:
    total_month_index = d.month - 1 + months
    year = d.year + total_month_index // 12
    month = total_month_index % 12 + 1
    last_day_of_target_month = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day_of_target_month)
    return date(year, month, day)


def generate_next_occurrence(recurrence_rule, after_date: date) -> date:
    """Returns the next occurrence date strictly after `after_date`."""
    frequency = recurrence_rule.frequency
    interval = max(1, recurrence_rule.interval)

    if frequency == RecurrenceFrequency.DAILY:
        return after_date + timedelta(days=interval)

    if frequency == RecurrenceFrequency.WEEKLY:
        return after_date + timedelta(days=7 * interval)

    if frequency == RecurrenceFrequency.MONTHLY:
        return _add_months(after_date, interval)

    if frequency == RecurrenceFrequency.CUSTOM_WEEKDAYS:
        weekdays = recurrence_rule.weekdays or []
        if not weekdays:
            raise ValueError("custom_weekdays recurrence requires at least one weekday")
        for offset in range(1, 8):
            candidate = after_date + timedelta(days=offset)
            if candidate.weekday() in weekdays:
                return candidate
        raise ValueError("no matching weekday found within 7 days")

    raise ValueError(f"Unknown recurrence frequency: {frequency}")
