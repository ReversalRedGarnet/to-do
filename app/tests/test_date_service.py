"""core/date_service.py — pure date-only helpers."""

from datetime import date, timedelta

from app.core.date_service import (
    month_end, next_month_start, normalize_due_date, week_end,
)

TODAY = date(2026, 6, 15)  # a Monday


def test_none_due_date_passes_through_unchanged():
    assert normalize_due_date(None, TODAY) is None


def test_future_due_date_is_unchanged():
    future = TODAY + timedelta(days=3)
    assert normalize_due_date(future, TODAY) == future


def test_todays_due_date_is_unchanged():
    assert normalize_due_date(TODAY, TODAY) == TODAY


def test_past_due_date_is_clamped_to_today():
    past = TODAY - timedelta(days=5)
    assert normalize_due_date(past, TODAY) == TODAY


def test_as_of_defaults_to_real_today(monkeypatch):
    from app.core import date_service
    monkeypatch.setattr(date_service, "today", lambda: TODAY)
    past = TODAY - timedelta(days=1)
    assert date_service.normalize_due_date(past) == TODAY


def test_week_end_is_sunday_of_the_same_week():
    assert week_end(TODAY) == date(2026, 6, 21)


def test_month_end_is_the_last_day_of_the_month():
    assert month_end(TODAY) == date(2026, 6, 30)


def test_month_end_handles_february_in_a_non_leap_year():
    assert month_end(date(2026, 2, 10)) == date(2026, 2, 28)


def test_month_end_handles_february_in_a_leap_year():
    assert month_end(date(2028, 2, 10)) == date(2028, 2, 29)


def test_next_month_start_is_the_1st_of_next_month():
    assert next_month_start(TODAY) == date(2026, 7, 1)


def test_next_month_start_rolls_over_the_year_boundary():
    assert next_month_start(date(2026, 12, 15)) == date(2027, 1, 1)


def test_month_end_rolls_over_the_year_boundary():
    assert month_end(date(2026, 12, 15)) == date(2026, 12, 31)
