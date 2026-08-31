"""Unit tests for core.recurrence_engine.generate_next_occurrence."""

from datetime import date

import pytest

from app.core.recurrence_engine import generate_next_occurrence
from app.models.recurrence import RecurrenceFrequency, RecurrenceRule


def rule(frequency, interval=1, weekdays=None):
    return RecurrenceRule(id=1, frequency=frequency, interval=interval, weekdays=weekdays)


def test_daily_advances_by_interval_days():
    next_date = generate_next_occurrence(rule(RecurrenceFrequency.DAILY), date(2026, 6, 15))
    assert next_date == date(2026, 6, 16)


def test_daily_respects_custom_interval():
    next_date = generate_next_occurrence(rule(RecurrenceFrequency.DAILY, interval=3), date(2026, 6, 15))
    assert next_date == date(2026, 6, 18)


def test_weekly_advances_by_seven_days():
    next_date = generate_next_occurrence(rule(RecurrenceFrequency.WEEKLY), date(2026, 6, 15))
    assert next_date == date(2026, 6, 22)


def test_weekly_respects_custom_interval():
    next_date = generate_next_occurrence(rule(RecurrenceFrequency.WEEKLY, interval=2), date(2026, 6, 15))
    assert next_date == date(2026, 6, 29)


def test_monthly_advances_same_day_next_month():
    next_date = generate_next_occurrence(rule(RecurrenceFrequency.MONTHLY), date(2026, 6, 15))
    assert next_date == date(2026, 7, 15)


def test_monthly_clamps_at_month_end():
    # Jan 31 + 1 month -> Feb has 28 days in 2026 (not a leap year)
    next_date = generate_next_occurrence(rule(RecurrenceFrequency.MONTHLY), date(2026, 1, 31))
    assert next_date == date(2026, 2, 28)


def test_monthly_respects_custom_interval_across_year_boundary():
    next_date = generate_next_occurrence(rule(RecurrenceFrequency.MONTHLY, interval=2), date(2026, 11, 30))
    assert next_date == date(2027, 1, 30)


def test_custom_weekdays_finds_next_matching_day():
    # Monday 2026-06-15; weekdays {2, 4} = Wednesday, Friday
    next_date = generate_next_occurrence(
        rule(RecurrenceFrequency.CUSTOM_WEEKDAYS, weekdays=[2, 4]), date(2026, 6, 15)
    )
    assert next_date == date(2026, 6, 17)  # Wednesday


def test_custom_weekdays_wraps_to_next_week_when_needed():
    # Friday 2026-06-19; weekdays {0} = Monday -> next Monday
    next_date = generate_next_occurrence(
        rule(RecurrenceFrequency.CUSTOM_WEEKDAYS, weekdays=[0]), date(2026, 6, 19)
    )
    assert next_date == date(2026, 6, 22)


def test_custom_weekdays_requires_at_least_one_weekday():
    with pytest.raises(ValueError):
        generate_next_occurrence(rule(RecurrenceFrequency.CUSTOM_WEEKDAYS, weekdays=[]), date(2026, 6, 15))
