"""Unit tests for project behavior. See spec §54."""

from datetime import date

import pytest

from app.core.state_engine import Color, derive_color, derive_project_color
from app.database.db import get_connection, initialize_database
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.task_service import TaskService

TODAY = date(2026, 6, 15)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def task_service(conn):
    return TaskService(TaskRepository(conn), NullNotificationService())


def make_child(project_id, **overrides):
    defaults = dict(
        id=None, title="Child", description="", task_type=TaskType.PROJECT_CHILD,
        project_id=project_id, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, available_from=TODAY, due_date=None,
        status=TaskStatus.PENDING, created_at=TODAY,
    )
    defaults.update(overrides)
    return Task(**defaults)


# - project remains purple
def test_project_remains_purple_regardless_of_child_state():
    assert derive_project_color() == Color.PURPLE

    missed_child = make_child(1, times_ignored=5, status=TaskStatus.SCHEDULED)
    assert derive_color(missed_child, TODAY, {}) == Color.RED
    # The project's own color is never derived from a child's state.
    assert derive_project_color() == Color.PURPLE


# - child task is schedulable
def test_child_task_is_schedulable(conn):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))

    task_repo = TaskRepository(conn)
    child = make_child(project_id)
    child_id = task_repo.create(child)

    fetched = task_repo.get_by_id(child_id)
    assert fetched.task_type == TaskType.PROJECT_CHILD
    assert fetched.project_id == project_id
    assert fetched.status == TaskStatus.PENDING  # eligible for generate_weekly_schedule


# - completing one child updates project progress
def test_completing_one_child_updates_project_progress(conn, task_service):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))

    task_repo = TaskRepository(conn)
    child_a = task_repo.create(make_child(project_id))
    child_b = task_repo.create(make_child(project_id))

    assert task_service.project_progress(project_id) == 0

    task_service.complete_task(child_a, completed_on=TODAY)

    assert task_service.project_progress(project_id) == 50

    task_service.complete_task(child_b, completed_on=TODAY)

    assert task_service.project_progress(project_id) == 100


def test_next_actionable_item_skips_completed_children(conn, task_service):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))

    task_repo = TaskRepository(conn)
    done = task_repo.create(make_child(project_id, due_date=date(2026, 6, 16)))
    next_up = task_repo.create(make_child(project_id, due_date=date(2026, 6, 20)))

    task_service.complete_task(done, completed_on=TODAY)

    result = task_service.next_actionable_item(project_id)
    assert result.id == next_up
