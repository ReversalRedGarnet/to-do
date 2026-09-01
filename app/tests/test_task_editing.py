"""Phase 2: compact task editing — double-click opens the existing
TaskEditorDialog directly, and Escape must close it without touching the
DB (Qt's default QDialog reject path; save only ever happens in _save()).

Also covers the editor's own Delete button (hardening follow-up): it must
delegate to a caller-supplied `on_delete` callback — the exact same
`_on_delete_requested` handler the context-menu path already uses, never
a second delete implementation — and must never invoke `_save()`."""

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

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


def _find_delete_button(dialog):
    for button in dialog.findChildren(QPushButton):
        if button.text() == "Delete":
            return button
    return None


def test_no_delete_button_when_on_delete_is_not_wired(wiring):
    task = make_task(wiring)
    dialog = TaskEditorDialog(task, wiring["category_repo"].list_all(), wiring["task_service"])

    assert _find_delete_button(dialog) is None


def test_delete_button_present_when_on_delete_is_wired(wiring):
    task = make_task(wiring)
    dialog = TaskEditorDialog(
        task, wiring["category_repo"].list_all(), wiring["task_service"], on_delete=lambda tid: True,
    )

    assert _find_delete_button(dialog) is not None


def test_delete_button_delegates_to_on_delete_and_closes_without_saving(wiring):
    task = make_task(wiring)
    dialog = TaskEditorDialog(
        task, wiring["category_repo"].list_all(), wiring["task_service"], on_delete=lambda tid: True,
    )
    dialog._title.setText("Mutated but should never be saved")
    update_calls = []
    wiring["task_service"].update_task = lambda *a, **k: update_calls.append((a, k))

    _find_delete_button(dialog).click()

    assert update_calls == []  # _save() must never run on the delete path
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_delete_button_passes_the_edited_tasks_id_to_on_delete(wiring):
    task = make_task(wiring)
    received = []
    dialog = TaskEditorDialog(
        task, wiring["category_repo"].list_all(), wiring["task_service"],
        on_delete=lambda tid: received.append(tid) or True,
    )

    _find_delete_button(dialog).click()

    assert received == [task.id]


def test_delete_button_keeps_the_dialog_open_when_on_delete_declines(wiring):
    """`on_delete` returns False when e.g. the confirmation prompt it
    shows is declined — the editor must not close (or discard the
    caller's in-progress edits) in that case."""
    task = make_task(wiring)
    dialog = TaskEditorDialog(
        task, wiring["category_repo"].list_all(), wiring["task_service"], on_delete=lambda tid: False,
    )
    reject_calls = []
    dialog.reject = lambda: reject_calls.append(True)

    _find_delete_button(dialog).click()

    assert reject_calls == []
