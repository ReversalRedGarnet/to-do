"""Unit tests for core.state_engine.reconcile. See spec §19, §54.

Required gap scenarios: 0, 1, 5, and 10+ days, including gaps that cross
one and two weekly boundaries. This is the most safety-critical module
in the app — do not skip edge cases here.
"""

from datetime import date, timedelta

from app.core.state_engine import Color, reconcile
from app.models.task import Task, TaskStatus, TaskType

MONDAY = date(2026, 6, 15)


def make_task(task_id, **overrides):
    defaults = dict(
        id=task_id,
        title=f"Task {task_id}",
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


def build_db_state(tasks, schedule):
    return {
        "tasks": {t.id: t for t in tasks},
        "schedule": schedule,
        "weekly_history": [],
    }


# - previous day closes correctly
# - new day becomes active
def test_zero_day_gap_replays_nothing():
    task = make_task(1)
    db_state = build_db_state([task], {MONDAY: [1]})

    result = reconcile(MONDAY, MONDAY, db_state)

    assert result.reconciled_dates == []
    assert result.tasks_marked_missed == []
    assert task.times_ignored == 0


# - missed tasks are reconciled
# - schedule recalculates (today's board reflects the new day)
def test_one_day_gap_marks_missed_task_orange():
    tuesday = MONDAY + timedelta(days=1)
    task = make_task(1, status=TaskStatus.SCHEDULED)
    db_state = build_db_state([task], {MONDAY: [1]})

    result = reconcile(MONDAY, tuesday, db_state)

    assert result.reconciled_dates == [MONDAY]
    assert result.tasks_marked_missed == [1]
    assert task.times_ignored == 1
    assert task.status == TaskStatus.PENDING
    assert (1, None, Color.ORANGE) in result.state_transitions


def test_one_day_gap_does_not_count_deliberate_defer_as_missed():
    tuesday = MONDAY + timedelta(days=1)
    task = make_task(1, status=TaskStatus.DEFERRED, deferred_at=MONDAY)
    db_state = build_db_state([task], {MONDAY: [1]})

    result = reconcile(MONDAY, tuesday, db_state)

    assert result.tasks_marked_missed == []
    assert task.times_ignored == 0


# - multi-day gap replays each day in order
def test_five_day_gap_replays_each_day_and_escalates_to_red():
    saturday = MONDAY + timedelta(days=5)
    task = make_task(1, status=TaskStatus.SCHEDULED)
    schedule = {
        MONDAY + timedelta(days=i): [1] for i in range(0, 5)  # Mon..Fri
    }
    db_state = build_db_state([task], schedule)

    result = reconcile(MONDAY, saturday, db_state)

    expected_days = [MONDAY + timedelta(days=i) for i in range(0, 5)]
    assert result.reconciled_dates == expected_days
    assert task.times_ignored == 5
    # Orange at the first miss, Red once the 3rd consecutive miss lands.
    assert (1, None, Color.ORANGE) in result.state_transitions
    assert (1, Color.ORANGE, Color.RED) in result.state_transitions


def test_ten_plus_day_gap_crosses_two_week_boundaries_and_purges_history():
    two_weeks_later = MONDAY + timedelta(days=14)
    task = make_task(1, status=TaskStatus.COMPLETED, completed_at=MONDAY)
    schedule = {MONDAY: [1]}
    db_state = build_db_state([task], schedule)

    result = reconcile(MONDAY, two_weeks_later, db_state)

    assert len(result.reconciled_dates) == 14  # Mon.. the day before two_weeks_later
    assert len(result.weeks_archived) == 2
    first_week, second_week = result.weeks_archived
    assert first_week["week_start"] == MONDAY
    assert second_week["week_start"] == MONDAY + timedelta(days=7)

    # Only the immediately preceding completed week is retained (spec §22).
    assert len(db_state["weekly_history"]) == 1
    assert db_state["weekly_history"][0]["week_start"] == second_week["week_start"]


def test_gap_crossing_single_week_boundary_archives_exactly_one_week():
    next_monday = MONDAY + timedelta(days=7)
    task = make_task(1, status=TaskStatus.SCHEDULED)
    db_state = build_db_state([task], {MONDAY: [1]})

    result = reconcile(MONDAY, next_monday, db_state)

    assert len(result.weeks_archived) == 1
    assert result.weeks_archived[0]["week_start"] == MONDAY
    assert 1 in result.weeks_archived[0]["missed_task_ids"]


def test_new_today_board_reflects_recalculated_state():
    tuesday = MONDAY + timedelta(days=1)
    missed_task = make_task(1, status=TaskStatus.SCHEDULED)
    today_task = make_task(2, status=TaskStatus.SCHEDULED, due_date=tuesday)
    db_state = build_db_state(
        [missed_task, today_task], {MONDAY: [1], tuesday: [2]}
    )

    result = reconcile(MONDAY, tuesday, db_state)

    board_by_id = {entry["task_id"]: entry["color"] for entry in result.new_today_board}
    assert board_by_id[2] == Color.YELLOW
