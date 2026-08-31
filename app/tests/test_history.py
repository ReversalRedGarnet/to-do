"""Unit tests for services.history_service. See spec §54."""

from datetime import date, timedelta

import pytest

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.history_repository import HistoryRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskType
from app.services.history_service import HistoryService

WEEK1 = date(2026, 6, 1)
WEEK2 = WEEK1 + timedelta(days=7)
WEEK3 = WEEK2 + timedelta(days=7)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def history_service(conn):
    return HistoryService(HistoryRepository(conn))


# - only previous completed week is retained
def test_only_previous_completed_week_is_retained(history_service, conn):
    history_service.archive_week(WEEK1, WEEK1 + timedelta(days=6), {"completed_task_ids": []})
    history_service.archive_week(WEEK2, WEEK2 + timedelta(days=6), {"completed_task_ids": []})

    repo = HistoryRepository(conn)
    remaining = repo.list_all()
    assert len(remaining) == 1
    assert remaining[0].week_start == WEEK2


def test_three_weeks_archived_only_keeps_the_last(history_service, conn):
    for week_start in (WEEK1, WEEK2, WEEK3):
        history_service.archive_week(week_start, week_start + timedelta(days=6), {})

    remaining = HistoryRepository(conn).list_all()
    assert len(remaining) == 1
    assert remaining[0].week_start == WEEK3


# - active/future tasks are preserved
def test_active_and_future_tasks_survive_history_purge(conn, history_service):
    task_repo = TaskRepository(conn)
    active = Task(
        id=None, title="Active task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=WEEK1, due_date=None,
        status=TaskStatus.PENDING, created_at=WEEK1,
    )
    future = Task(
        id=None, title="Future task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=WEEK3, due_date=None,
        status=TaskStatus.PENDING, created_at=WEEK1,
    )
    active_id = task_repo.create(active)
    future_id = task_repo.create(future)

    history_service.archive_week(WEEK1, WEEK1 + timedelta(days=6), {})
    history_service.archive_week(WEEK2, WEEK2 + timedelta(days=6), {})

    assert task_repo.get_by_id(active_id) is not None
    assert task_repo.get_by_id(future_id) is not None


# - projects are preserved
def test_projects_are_preserved_across_history_purge(conn, history_service):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))

    history_service.archive_week(WEEK1, WEEK1 + timedelta(days=6), {})
    history_service.archive_week(WEEK2, WEEK2 + timedelta(days=6), {})

    assert project_repo.get_by_id(project_id) is not None


# - recurring definitions are preserved
def test_recurrence_rules_are_preserved_across_history_purge(conn, history_service):
    conn.execute(
        "INSERT INTO recurrence_rules (frequency, interval, created_at) VALUES (?, ?, ?)",
        ("weekly", 1, WEEK1.isoformat()),
    )
    conn.commit()

    history_service.archive_week(WEEK1, WEEK1 + timedelta(days=6), {})
    history_service.archive_week(WEEK2, WEEK2 + timedelta(days=6), {})

    row = conn.execute("SELECT COUNT(*) AS n FROM recurrence_rules").fetchone()
    assert row["n"] == 1


def test_apply_reconciliation_archives_persists_reconcile_output(conn, history_service):
    weeks_archived = [
        {
            "week_start": WEEK1,
            "week_end": WEEK1 + timedelta(days=6),
            "completed_task_ids": [1],
            "missed_task_ids": [2],
            "deferred_task_ids": [],
        },
        {
            "week_start": WEEK2,
            "week_end": WEEK2 + timedelta(days=6),
            "completed_task_ids": [],
            "missed_task_ids": [],
            "deferred_task_ids": [3],
        },
    ]
    history_service.apply_reconciliation_archives(weeks_archived)

    repo = HistoryRepository(conn)
    remaining = repo.list_all()
    assert len(remaining) == 1
    assert remaining[0].week_start == WEEK2
    assert repo.get_snapshot(WEEK2)["deferred_task_ids"] == [3]
