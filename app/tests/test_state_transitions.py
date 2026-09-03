"""Unit tests for color/state derivation. See spec §54."""

from datetime import date, timedelta

from app.core.state_engine import Color, derive_color
from app.models.task import Task, TaskStatus, TaskType

TODAY = date(2026, 6, 17)


def make_task(**overrides):
    defaults = dict(
        id=1,
        title="Task",
        description="",
        task_type=TaskType.NORMAL,
        project_id=None,
        category="Personal",
        importance=3,
        urgency=3,
        seriousness=3,
        effort=1,
        due_date=None,
        status=TaskStatus.SCHEDULED,
    )
    defaults.update(overrides)
    return Task(**defaults)


# - first missed opportunity -> orange
def test_first_missed_opportunity_is_orange():
    task = make_task(times_ignored=1)
    assert derive_color(task, TODAY, {}) == Color.ORANGE


# - repeated ignored opportunities -> red
def test_repeated_ignored_opportunities_are_red():
    task = make_task(times_ignored=3)
    assert derive_color(task, TODAY, {}) == Color.RED


def test_not_yet_missed_is_not_orange_or_red():
    task = make_task(times_ignored=0)
    assert derive_color(task, TODAY, {}) not in (Color.ORANGE, Color.RED)


# - deliberate defer does not count as ignore
def test_deliberate_defer_produces_no_punitive_color():
    task = make_task(status=TaskStatus.DEFERRED, deferred_at=TODAY, times_ignored=0)
    assert derive_color(task, TODAY, {}) not in (Color.ORANGE, Color.RED)


# - completing early produces green
def test_completing_ahead_of_expected_date_is_green():
    task = make_task(
        status=TaskStatus.COMPLETED,
        completed_at=TODAY,
    )
    context = {"expected_date": TODAY + timedelta(days=3)}
    assert derive_color(task, TODAY, context) == Color.GREEN


def test_completing_on_expected_date_is_not_green():
    task = make_task(status=TaskStatus.COMPLETED, completed_at=TODAY)
    context = {"expected_date": TODAY}
    assert derive_color(task, TODAY, context) != Color.GREEN


def test_due_today_is_yellow():
    task = make_task(due_date=TODAY, times_ignored=0)
    assert derive_color(task, TODAY, {}) == Color.YELLOW


def test_fixed_event_is_always_blue():
    task = make_task(task_type=TaskType.FIXED_EVENT, times_ignored=5)
    assert derive_color(task, TODAY, {}) == Color.BLUE
