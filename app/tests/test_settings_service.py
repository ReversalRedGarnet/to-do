"""Unit tests for services.settings_service and ScheduleService's use of
settings.daily_capacities (spec §27/§47 — Settings must actually affect
scheduling, not just be editable and silently ignored)."""

from datetime import date, timedelta

import pytest

from app.config.settings import Capacity, DEFAULT_WEEKLY_CAPACITY
from app.database.db import get_connection, initialize_database
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.settings_repository import SettingsRepository
from app.database.repositories.task_repository import TaskRepository
from app.models.task import Task, TaskStatus, TaskType
from app.services.schedule_service import ScheduleService
from app.services.settings_service import SettingsService

MONDAY = date(2026, 6, 15)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    """generate_weekly_schedule now excludes days before "today" from new
    placements (audit fix #3) — pin today to the start of the fixed MONDAY
    week these tests plan around, so none of that week is treated as
    already elapsed relative to whatever date the suite actually runs on."""
    from app.core import date_service
    monkeypatch.setattr(date_service, "today", lambda: MONDAY)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


def test_get_returns_the_seeded_defaults(conn):
    service = SettingsService(SettingsRepository(conn))
    settings = service.get()
    assert settings.notifications_enabled is True
    assert settings.sunday_reminder_enabled is True
    assert len(settings.daily_capacities) == 7


def test_update_is_partial(conn):
    service = SettingsService(SettingsRepository(conn))
    service.update(notifications_enabled=False)

    settings = service.get()
    assert settings.notifications_enabled is False
    assert settings.sunday_reminder_enabled is True  # untouched


def test_update_daily_capacities_round_trips(conn):
    service = SettingsService(SettingsRepository(conn))
    new_capacities = ["LOW", "LOW", "LOW", "LOW", "LOW", "LOW", "LOW"]
    service.update(daily_capacities=new_capacities)

    assert service.get().daily_capacities == new_capacities


def make_task(**overrides):
    defaults = dict(
        id=None, title="Task", description="", task_type=TaskType.NORMAL,
        project_id=None, category="Personal", importance=3, urgency=3,
        seriousness=3, effort=1, due_date=MONDAY + timedelta(days=6),
        status=TaskStatus.PENDING, created_at=MONDAY,
    )
    defaults.update(overrides)
    return Task(**defaults)


def test_generate_week_uses_settings_capacities_when_not_passed_explicitly(conn):
    task_repo = TaskRepository(conn)
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)
    settings_repo = SettingsRepository(conn)

    # Shrink every day to LOW capacity via Settings.
    SettingsService(settings_repo).update(
        daily_capacities=["LOW"] * 7
    )

    task_repo.create(make_task(effort=5))  # cost 8; LOW*0.75=2.25, won't fit anywhere

    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo, settings_repo)
    schedule = schedule_service.generate_week(MONDAY)

    placements = [p for placements in schedule.values() for p in placements]
    assert len(placements) == 1
    assert placements[0].overcommitted is True  # confirms LOW capacity was actually used


def test_generate_week_falls_back_to_default_without_settings_repository(conn):
    task_repo = TaskRepository(conn)
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)

    task_repo.create(make_task(effort=1))

    # No settings_repository passed — must not raise, must use the v1 default.
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    schedule = schedule_service.generate_week(MONDAY)

    placements = [p for placements in schedule.values() for p in placements]
    assert len(placements) == 1
    assert placements[0].overcommitted is False  # plenty of room under MEDIUM/HIGH/LOW default


def test_explicit_capacities_argument_still_overrides_settings(conn):
    task_repo = TaskRepository(conn)
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)
    settings_repo = SettingsRepository(conn)
    SettingsService(settings_repo).update(daily_capacities=["LOW"] * 7)

    task_repo.create(make_task(effort=1))

    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo, settings_repo)
    schedule = schedule_service.generate_week(MONDAY, capacities=DEFAULT_WEEKLY_CAPACITY)

    placements = [p for placements in schedule.values() for p in placements]
    assert placements[0].overcommitted is False


# --- Audit item: settings fallbacks must log a warning, not fail silently ---

def test_corrupted_daily_capacities_logs_a_warning_and_falls_back(conn, caplog):
    import json
    conn.execute("UPDATE settings SET daily_capacities = ? WHERE id = 1", (json.dumps(["BOGUS"]),))
    conn.commit()
    settings_repo = SettingsRepository(conn)
    schedule_service = ScheduleService(
        TaskRepository(conn), ScheduleRepository(conn), FixedEventRepository(conn), settings_repo,
    )

    with caplog.at_level("WARNING", logger="app.services.schedule_service"):
        capacities = schedule_service._default_capacities()

    assert capacities == DEFAULT_WEEKLY_CAPACITY
    assert any("daily_capacities" in record.message for record in caplog.records)
    assert any(record.levelname == "WARNING" for record in caplog.records)


class _BrokenSettingsRepository:
    """Stands in for a settings row that's present but structurally
    broken (e.g. a schema/migration mismatch) — `.get()` returning
    something that doesn't have the expected week_gen_* attributes is
    exactly the AttributeError `_week_gen_settings` guards against."""

    def get(self):
        return None


def test_corrupted_week_gen_settings_logs_a_warning_and_falls_back(caplog):
    schedule_service = ScheduleService(None, None, None, _BrokenSettingsRepository())

    with caplog.at_level("WARNING", logger="app.services.schedule_service"):
        weekend_allowed, allow_automove, target = schedule_service._week_gen_settings()

    assert (weekend_allowed, allow_automove) == (True, True)
    assert any("week-generation" in record.message for record in caplog.records)
    assert any(record.levelname == "WARNING" for record in caplog.records)
