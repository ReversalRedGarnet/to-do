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
from app.services.project_service import ProjectService
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


# --- Phase 5: due date, open count, grouping, archive ---

def test_project_due_date_round_trips_through_the_repository(conn):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Launch", description="", due_date=date(2026, 7, 1)))

    fetched = project_repo.get_by_id(project_id)

    assert fetched.due_date == date(2026, 7, 1)


def test_project_service_create_and_archive(conn):
    service = ProjectService(ProjectRepository(conn))
    project = service.create("Launch", "Ship it", date(2026, 7, 1))

    assert project.id is not None
    assert project in service.list_active()

    service.archive(project.id)

    assert project.id not in {p.id for p in service.list_active()}
    assert project.id in {p.id for p in service.list_archived()}


def test_count_open_tasks_excludes_completed_and_cancelled(conn, task_service):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))
    task_repo = TaskRepository(conn)
    open_a = task_repo.create(make_child(project_id))
    open_b = task_repo.create(make_child(project_id, status=TaskStatus.SCHEDULED))
    done = task_repo.create(make_child(project_id))
    task_service.complete_task(done, completed_on=TODAY)

    assert task_service.count_open_tasks(project_id) == 2


def test_tasks_grouped_by_status(conn, task_service):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))
    task_repo = TaskRepository(conn)
    pending_id = task_repo.create(make_child(project_id, status=TaskStatus.PENDING))
    done_id = task_repo.create(make_child(project_id))
    task_service.complete_task(done_id, completed_on=TODAY)

    groups = task_service.tasks_grouped_by_status(project_id)

    assert [t.id for t in groups[TaskStatus.PENDING]] == [pending_id]
    assert [t.id for t in groups[TaskStatus.COMPLETED]] == [done_id]


def test_assigning_a_project_flips_a_normal_task_to_project_child(conn, task_service):
    project_repo = ProjectRepository(conn)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))
    task_repo = TaskRepository(conn)
    task_id = task_repo.create(Task(
        id=None, title="Loose task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3, seriousness=3,
        effort=1, available_from=TODAY, due_date=None, status=TaskStatus.PENDING, created_at=TODAY,
    ))

    task_service.update_task(task_id, project_id=project_id)
    linked = task_repo.get_by_id(task_id)
    assert linked.task_type == TaskType.PROJECT_CHILD

    task_service.update_task(task_id, project_id=None)
    unlinked = task_repo.get_by_id(task_id)
    assert unlinked.task_type == TaskType.NORMAL


# --- Audit item: archiving a project excludes its children from week
#     planning/Today without deleting or force-completing them ---

def test_archiving_a_project_excludes_its_children_from_week_eligibility(conn, task_service):
    project_repo = ProjectRepository(conn)
    project_service = ProjectService(project_repo)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))
    task_repo = TaskRepository(conn)
    child_id = task_repo.create(make_child(project_id))

    week_start, week_end = date(2026, 6, 15), date(2026, 6, 21)
    assert child_id in {t.id for t in task_repo.list_eligible_for_week(week_start, week_end)}

    project_service.archive(project_id)

    assert child_id not in {t.id for t in task_repo.list_eligible_for_week(week_start, week_end)}
    # Neither deleted nor force-completed — still there, still PENDING.
    still_there = task_repo.get_by_id(child_id)
    assert still_there is not None
    assert still_there.status == TaskStatus.PENDING


def test_unarchiving_a_project_restores_its_childrens_week_eligibility(conn, task_service):
    project_repo = ProjectRepository(conn)
    project_service = ProjectService(project_repo)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))
    task_repo = TaskRepository(conn)
    child_id = task_repo.create(make_child(project_id))
    project_service.archive(project_id)

    week_start, week_end = date(2026, 6, 15), date(2026, 6, 21)
    assert child_id not in {t.id for t in task_repo.list_eligible_for_week(week_start, week_end)}

    project_service.update(project_id, active=True)

    assert child_id in {t.id for t in task_repo.list_eligible_for_week(week_start, week_end)}


def test_archiving_a_project_excludes_its_children_from_today_view_task_list(conn, task_service):
    """TodayPanel/WeeklyBoard read via TaskService.list_all(exclude_
    archived_project_children=True) — the flag is opt-in so every other
    caller (search, project detail view, etc.) is unaffected."""
    project_repo = ProjectRepository(conn)
    project_service = ProjectService(project_repo)
    project_id = project_repo.create(Project(id=None, name="Build Todo App", description=""))
    task_repo = TaskRepository(conn)
    child_id = task_repo.create(make_child(project_id))

    assert child_id in {t.id for t in task_service.list_all(exclude_archived_project_children=True)}

    project_service.archive(project_id)

    assert child_id not in {t.id for t in task_service.list_all(exclude_archived_project_children=True)}
    # Unaffected callers still see it — e.g. the project's own detail view.
    assert child_id in {t.id for t in task_service.list_all()}
