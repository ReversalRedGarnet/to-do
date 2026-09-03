"""core/date_service.py — pure date-only helpers."""

from datetime import date, timedelta

from app.core.date_service import normalize_due_date

TODAY = date(2026, 6, 15)


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
