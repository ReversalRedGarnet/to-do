"""Phase 2: compact task editing — double-click opens the existing
TaskEditorDialog directly, and Escape must close it without touching the
DB (Qt's default QDialog reject path; save only ever happens in _save())."""

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from app.database.db import get_connection, initialize_database
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.task import Task, TaskStatus, TaskType
from app.notifications.notification_service import NullNotificationService
from app.services.task_service import TaskService
from app.ui.task_editor import TaskEditorDialog
from app.ui.widgets.task_card import TaskCard

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


def make_task(wiring, **overrides):
    defaults = dict(
        id=None, title="Original title", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=2, available_from=TODAY, due_date=None,
        status=TaskStatus.PENDING, created_at=TODAY,
    )
    defaults.update(overrides)
    task_id = wiring["task_repo"].create(Task(**defaults))
    return wiring["task_repo"].get_by_id(task_id)


def test_double_click_on_a_card_emits_edit_clicked(wiring):
    task = make_task(wiring)
    card = TaskCard(task, None)

    received = []
    card.edit_clicked.connect(received.append)
    QTest.mouseDClick(card, Qt.MouseButton.LeftButton)

    assert received == [task.id]


def test_escape_closes_editor_without_saving_changes(wiring):
    task = make_task(wiring)
    dialog = TaskEditorDialog(task, wiring["category_repo"].list_all(), wiring["task_service"])
    dialog._title.setText("Mutated but never saved")

    QTest.keyClick(dialog, Qt.Key.Key_Escape)

    assert dialog.result() == QDialog.DialogCode.Rejected
    unchanged = wiring["task_repo"].get_by_id(task.id)
    assert unchanged.title == "Original title"
