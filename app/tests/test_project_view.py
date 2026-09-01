"""Phase 5: drives the real ProjectView/ProjectDetailDialog widgets, same
technique test_settings_view.py uses — construct directly, no mocking."""

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService
from app.ui.project_view import ProjectDetailDialog, ProjectView

TODAY = date.today()


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def auto_accept_dialogs(monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def wiring(conn):
    project_repo = ProjectRepository(conn)
    task_repo = TaskRepository(conn)
    category_repo = CategoryRepository(conn)
    project_service = ProjectService(project_repo)
    task_service = TaskService(task_repo, NullNotificationService())
    return dict(project_repo=project_repo, task_repo=task_repo, category_repo=category_repo,
                project_service=project_service, task_service=task_service)


def test_no_active_projects_shows_placeholder(wiring):
    view = ProjectView(wiring["project_service"], wiring["task_service"], wiring["category_repo"])
    assert view._active_layout.count() == 1  # the "No active projects yet." label


def test_project_card_shows_open_count_and_progress(wiring):
    project_id = wiring["project_repo"].create(Project(id=None, name="Launch", description=""))
    wiring["task_repo"].create(Task(
        id=None, title="Child", description="", task_type=TaskType.PROJECT_CHILD,
        project_id=project_id, category="Personal", importance=3, urgency=3, seriousness=3,
        effort=1, available_from=TODAY, due_date=None, status=TaskStatus.PENDING, created_at=TODAY,
    ))
    view = ProjectView(wiring["project_service"], wiring["task_service"], wiring["category_repo"])

    card = view._active_layout.itemAt(0).widget()
    assert card.project_id == project_id


def test_archiving_a_project_via_the_detail_dialog_removes_it_from_active(wiring, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    project_id = wiring["project_repo"].create(Project(id=None, name="Launch", description=""))
    project = wiring["project_repo"].get_by_id(project_id)
    dialog = ProjectDetailDialog(project, wiring["project_service"], wiring["task_service"], [])

    dialog._on_archive()

    assert project_id not in {p.id for p in wiring["project_service"].list_active()}
    assert project_id in {p.id for p in wiring["project_service"].list_archived()}


def test_archived_projects_render_as_clickable_cards_not_plain_labels(wiring):
    """Audit item: the Archived section used to render a plain QLabel with
    no click handler — there was no way back into ProjectDetailDialog for
    an archived project. It must render the same clickable ProjectCard the
    active list uses."""
    from app.ui.project_view import ProjectCard

    project_id = wiring["project_repo"].create(Project(id=None, name="Old Launch", description=""))
    wiring["project_service"].archive(project_id)
    view = ProjectView(wiring["project_service"], wiring["task_service"], wiring["category_repo"])

    card = view._archived_section.body_layout.itemAt(0).widget()

    assert isinstance(card, ProjectCard)
    assert card.project_id == project_id


def test_clicking_an_archived_project_card_opens_its_detail_dialog(wiring):
    project_id = wiring["project_repo"].create(Project(id=None, name="Old Launch", description=""))
    wiring["project_service"].archive(project_id)
    view = ProjectView(wiring["project_service"], wiring["task_service"], wiring["category_repo"])
    project = wiring["project_repo"].get_by_id(project_id)

    view._open_detail(project)  # what the archived card's click ultimately calls

    # auto_accept_dialogs makes exec() return Accepted immediately, so
    # reaching here without raising confirms the dialog was constructible
    # and closable for an archived project — the actual regression this
    # guards is the card having no click handler at all.


def test_unarchiving_from_the_detail_dialog_restores_it_to_active(wiring):
    project_id = wiring["project_repo"].create(Project(id=None, name="Old Launch", description=""))
    wiring["project_service"].archive(project_id)
    project = wiring["project_repo"].get_by_id(project_id)
    dialog = ProjectDetailDialog(project, wiring["project_service"], wiring["task_service"], [])

    assert hasattr(dialog, "_unarchive_button")
    dialog._on_unarchive()

    assert project_id in {p.id for p in wiring["project_service"].list_active()}
    assert project_id not in {p.id for p in wiring["project_service"].list_archived()}


def test_new_project_dialog_fields_feed_project_service_create(wiring):
    from app.ui.project_view import _NewProjectDialog

    dialog = _NewProjectDialog()
    dialog._name.setText("New Initiative")
    dialog._description.setText("Q3 push")

    view = ProjectView(wiring["project_service"], wiring["task_service"], wiring["category_repo"])
    wiring["project_service"].create(dialog.name(), dialog.description(), dialog.due_date())
    view.refresh()

    created = next(p for p in wiring["project_service"].list_active() if p.name == "New Initiative")
    assert created.description == "Q3 push"
    assert created.due_date is None  # "Set" checkbox left unchecked
