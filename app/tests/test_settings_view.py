"""Verifies the real SettingsView widget (spec §27/§47) — constructs it
directly and drives its controls, same technique as
test_task_editor_recurrence.py."""

import pytest
from PySide6.QtWidgets import QApplication

from app.database.db import get_connection, initialize_database
from app.database.repositories.settings_repository import SettingsRepository
from app.services.settings_service import SettingsService
from app.ui.settings_view import SettingsView


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
def settings_service(conn):
    return SettingsService(SettingsRepository(conn))


def test_view_prefills_from_current_settings(settings_service):
    view = SettingsView(settings_service)
    assert view._notifications_enabled.isChecked() is True
    assert view._sunday_reminder_enabled.isChecked() is True
    assert len(view._capacity_boxes) == 7
    assert view._capacity_boxes[5].currentText() == "HIGH"  # Saturday default
    assert view._capacity_boxes[6].currentText() == "LOW"   # Sunday default


def test_toggling_and_saving_notifications_persists(settings_service):
    view = SettingsView(settings_service)
    view._notifications_enabled.setChecked(False)

    view._save()

    assert settings_service.get().notifications_enabled is False


def test_changing_a_capacity_and_saving_persists_all_seven(settings_service):
    view = SettingsView(settings_service)
    view._capacity_boxes[0].setCurrentText("HIGH")  # Monday -> HIGH

    view._save()

    capacities = settings_service.get().daily_capacities
    assert capacities[0] == "HIGH"
    assert len(capacities) == 7


def test_refresh_reflects_changes_made_elsewhere(settings_service):
    view = SettingsView(settings_service)
    settings_service.update(notifications_enabled=False)

    view.refresh()

    assert view._notifications_enabled.isChecked() is False
