"""Unit tests for core.board_view — the Today view's Overdue/Today/
Unscheduled/Completed sectioning logic. Pure function, no DB/Qt."""

from datetime import date, timedelta

from app.core.board_view import build_today_sections
from app.models.task import Task, TaskStatus, TaskType

TODAY = date(2026, 6, 15)


def make_task(**overrides):
    defaults = dict(
        id=1, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=None, due_date=None,
        status=TaskStatus.PENDING, created_at=TODAY,
    )
    defaults.update(overrides)
    return Task(**defaults)


def test_task_scheduled_today_lands_in_today_bucket():
    task = make_task(id=1, status=TaskStatus.SCHEDULED)
    sections = build_today_sections([task], TODAY, {1})
    assert sections.today == [task]
    assert not sections.overdue and not sections.unscheduled and not sections.completed


def test_task_with_past_due_date_lands_in_overdue_even_if_scheduled_today():
    task = make_task(id=1, due_date=TODAY - timedelta(days=2), status=TaskStatus.SCHEDULED)
    sections = build_today_sections([task], TODAY, {1})
    assert sections.overdue == [task]
    assert sections.today == []  # overdue wins, not double-listed


def test_never_scheduled_active_task_lands_in_unscheduled():
    task = make_task(id=1, status=TaskStatus.PENDING)
    sections = build_today_sections([task], TODAY, set())
    assert sections.unscheduled == [task]


def test_task_due_later_and_not_scheduled_today_lands_in_unscheduled():
    task = make_task(id=1, due_date=TODAY + timedelta(days=5), status=TaskStatus.PENDING)
    sections = build_today_sections([task], TODAY, set())
    assert sections.unscheduled == [task]


def test_completed_task_lands_in_completed_regardless_of_due_date():
    task = make_task(id=1, due_date=TODAY - timedelta(days=3), status=TaskStatus.COMPLETED, completed_at=TODAY)
    sections = build_today_sections([task], TODAY, {1})
    assert sections.completed == [task]
    assert sections.overdue == [] and sections.today == []


def test_cancelled_task_appears_nowhere():
    task = make_task(id=1, status=TaskStatus.CANCELLED)
    sections = build_today_sections([task], TODAY, {1})
    assert not sections.overdue and not sections.today and not sections.unscheduled and not sections.completed


def test_sections_sort_by_priority_score_descending():
    low = make_task(id=1, importance=1, urgency=1, seriousness=1, status=TaskStatus.PENDING)
    high = make_task(id=2, importance=5, urgency=5, seriousness=5, status=TaskStatus.PENDING)
    sections = build_today_sections([low, high], TODAY, set())
    assert [t.id for t in sections.unscheduled] == [2, 1]
