"""Phase 7: Ctrl+F search — repository LIKE query, TaskService wrapper,
and the real SearchDialog widget."""

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.task_service import TaskService
from app.ui.search_dialog import SearchDialog

TODAY = date.today()


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def wiring(conn):
    task_repo = TaskRepository(conn)
    category_repo = CategoryRepository(conn)
    task_service = TaskService(task_repo, NullNotificationService())
    return dict(task_repo=task_repo, category_repo=category_repo, task_service=task_service)


def make_task(wiring, title, **overrides):
    defaults = dict(
        id=None, title=title, description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=None,
        status=TaskStatus.PENDING, created_at=TODAY,
    )
    defaults.update(overrides)
    return wiring["task_repo"].create(Task(**defaults))


def test_search_is_case_insensitive_substring_match(wiring):
    make_task(wiring, "Buy Groceries")
    make_task(wiring, "Call the dentist")

    results = wiring["task_service"].search_tasks("groc")

    assert [t.title for t in results] == ["Buy Groceries"]


def test_search_excludes_cancelled_tasks(wiring):
    task_id = make_task(wiring, "Old plan")
    wiring["task_service"].cancel_task(task_id)

    assert wiring["task_service"].search_tasks("Old") == []


def test_search_escapes_like_wildcards(wiring):
    make_task(wiring, "50% done milestone")
    make_task(wiring, "Something else entirely")

    results = wiring["task_service"].search_tasks("50%")

    assert [t.title for t in results] == ["50% done milestone"]


def test_empty_query_returns_no_results(wiring):
    make_task(wiring, "Anything")
    assert wiring["task_service"].search_tasks("   ") == []


def test_search_dialog_updates_results_as_query_changes(wiring):
    make_task(wiring, "Renew passport")
    dialog = SearchDialog(wiring["task_service"], wiring["category_repo"])

    dialog._input.setText("passport")

    assert dialog._results.count() == 1
    assert "Renew passport" in dialog._results.item(0).text()


def test_search_dialog_double_click_opens_editor(wiring, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    task_id = make_task(wiring, "Renew passport")
    dialog = SearchDialog(wiring["task_service"], wiring["category_repo"])
    dialog._input.setText("passport")

    dialog._on_result_activated(dialog._results.item(0))  # must not raise
