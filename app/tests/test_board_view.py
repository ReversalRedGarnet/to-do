"""Unit tests for core.board_view — the Today view's due-date sectioning
logic (Overdue / Today / Tomorrow / This Week / This Month / Next Month
or Later / Unscheduled / Completed). Pure function, no DB/Qt."""

from datetime import date, timedelta

from app.core import date_service
from app.core.board_view import build_today_sections
from app.models.task import Task, TaskStatus, TaskType

TODAY = date(2026, 6, 15)  # a Monday


def make_task(**overrides):
    defaults = dict(
        id=1, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=None,
        status=TaskStatus.PENDING, created_at=TODAY,
    )
    defaults.update(overrides)
    return Task(**defaults)


def _only(sections, name):
    """Assert every other bucket is empty and return the named one."""
    names = ("overdue", "today", "tomorrow", "this_week", "this_month",
              "next_month_or_later", "unscheduled", "completed")
    for n in names:
        if n != name:
            assert getattr(sections, n) == [], f"expected {n} empty, got {getattr(sections, n)}"
    return getattr(sections, name)


def test_task_with_no_due_date_lands_in_unscheduled():
    task = make_task(id=1, due_date=None)
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "unscheduled") == [task]


def test_task_due_yesterday_lands_in_overdue():
    task = make_task(id=1, due_date=TODAY - timedelta(days=1))
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "overdue") == [task]


def test_task_due_today_lands_in_today():
    task = make_task(id=1, due_date=TODAY)
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "today") == [task]


def test_task_due_tomorrow_lands_in_tomorrow():
    task = make_task(id=1, due_date=TODAY + timedelta(days=1))
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "tomorrow") == [task]


def test_task_due_day_after_tomorrow_lands_in_this_week():
    task = make_task(id=1, due_date=TODAY + timedelta(days=2))
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "this_week") == [task]


def test_task_due_exactly_at_week_end_lands_in_this_week():
    week_end = date_service.week_end(TODAY)
    task = make_task(id=1, due_date=week_end)
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "this_week") == [task]


def test_task_due_day_after_week_end_lands_in_this_month():
    week_end = date_service.week_end(TODAY)
    task = make_task(id=1, due_date=week_end + timedelta(days=1))
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "this_month") == [task]


def test_task_due_exactly_at_month_end_lands_in_this_month():
    month_end = date_service.month_end(TODAY)
    task = make_task(id=1, due_date=month_end)
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "this_month") == [task]


def test_task_due_first_of_next_month_lands_in_next_month_or_later():
    next_month = date_service.next_month_start(TODAY)
    task = make_task(id=1, due_date=next_month)
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "next_month_or_later") == [task]


def test_task_due_far_in_the_future_lands_in_next_month_or_later():
    task = make_task(id=1, due_date=TODAY + timedelta(days=400))
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "next_month_or_later") == [task]


def test_boundary_holds_when_the_week_spans_into_the_next_month():
    """Dec 29 2025 is a Monday whose Mon-Sun week runs into January —
    a task due inside that week but past the month boundary must still
    land in this_week (the week takes precedence over the raw month-end
    cutoff), while one due after the week is over lands in next month."""
    year_end_monday = date(2025, 12, 29)
    week_end = date_service.week_end(year_end_monday)  # 2026-01-04
    assert week_end == date(2026, 1, 4)

    in_week_next_year = make_task(id=1, due_date=date(2026, 1, 3))
    after_week = make_task(id=2, due_date=date(2026, 1, 5))
    sections = build_today_sections([in_week_next_year, after_week], year_end_monday)
    assert sections.this_week == [in_week_next_year]
    assert sections.next_month_or_later == [after_week]


def test_completed_task_lands_in_completed_regardless_of_due_date():
    task = make_task(id=1, due_date=TODAY - timedelta(days=3), status=TaskStatus.COMPLETED, completed_at=TODAY)
    sections = build_today_sections([task], TODAY)
    assert _only(sections, "completed") == [task]


def test_cancelled_task_appears_nowhere():
    task = make_task(id=1, status=TaskStatus.CANCELLED)
    sections = build_today_sections([task], TODAY)
    for name in ("overdue", "today", "tomorrow", "this_week", "this_month",
                 "next_month_or_later", "unscheduled", "completed"):
        assert getattr(sections, name) == []


def test_sections_sort_by_priority_score_descending():
    low = make_task(id=1, importance=1, urgency=1, seriousness=1, status=TaskStatus.PENDING)
    high = make_task(id=2, importance=5, urgency=5, seriousness=5, status=TaskStatus.PENDING)
    sections = build_today_sections([low, high], TODAY)
    assert [t.id for t in sections.unscheduled] == [2, 1]
