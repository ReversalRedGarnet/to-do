"""Unit tests for core.priority_engine. See spec §54."""

from datetime import date, timedelta

from app.core.priority_engine import (
    calculate_deadline_pressure,
    calculate_priority_score,
)
from app.models.task import Task, TaskStatus, TaskType

TODAY = date(2026, 6, 15)


def make_task(**overrides):
    defaults = dict(
        id=None,
        title="Task",
        description="",
        task_type=TaskType.NORMAL,
        project_id=None,
        category="Personal",
        importance=3,
        urgency=3,
        seriousness=3,
        effort=2,
        available_from=None,
        due_date=None,
        status=TaskStatus.PENDING,
    )
    defaults.update(overrides)
    return Task(**defaults)


# - high importance increases score
def test_high_importance_increases_score():
    low = make_task(importance=1)
    high = make_task(importance=5)
    assert calculate_priority_score(high, TODAY) > calculate_priority_score(low, TODAY)


# - high urgency increases score
def test_high_urgency_increases_score():
    low = make_task(urgency=1)
    high = make_task(urgency=5)
    assert calculate_priority_score(high, TODAY) > calculate_priority_score(low, TODAY)


# - high seriousness increases score
def test_high_seriousness_increases_score():
    low = make_task(seriousness=1)
    high = make_task(seriousness=5)
    assert calculate_priority_score(high, TODAY) > calculate_priority_score(low, TODAY)


# - closer deadline increases pressure
def test_closer_deadline_increases_pressure():
    far = calculate_deadline_pressure(TODAY + timedelta(days=14), TODAY)
    near = calculate_deadline_pressure(TODAY + timedelta(days=1), TODAY)
    assert near > far


def test_closer_deadline_increases_score_end_to_end():
    far_task = make_task(due_date=TODAY + timedelta(days=14))
    near_task = make_task(due_date=TODAY + timedelta(days=1))
    assert calculate_priority_score(near_task, TODAY) > calculate_priority_score(far_task, TODAY)


# - overdue deadline receives maximum pressure
def test_overdue_deadline_receives_maximum_pressure():
    overdue = calculate_deadline_pressure(TODAY - timedelta(days=5), TODAY)
    due_today = calculate_deadline_pressure(TODAY, TODAY)
    assert overdue == 5.0
    assert due_today == 5.0


def test_no_due_date_has_zero_pressure():
    assert calculate_deadline_pressure(None, TODAY) == 0.0
