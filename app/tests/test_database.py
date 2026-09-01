"""Phase 1 smoke tests: schema applies cleanly and seeds first-run defaults."""

import sqlite3

import pytest

from app.database.db import get_connection, initialize_database
from app.config.settings import DEFAULT_CATEGORIES


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


def test_initialize_creates_all_tables(db_path):
    initialize_database(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        names = {row["name"] for row in rows}
    finally:
        conn.close()

    expected = {
        "categories", "projects", "recurrence_rules", "tasks",
        "fixed_events", "task_schedule", "weekly_history", "settings",
        "app_state",
    }
    assert expected.issubset(names)


def test_initialize_is_idempotent(db_path):
    initialize_database(db_path)
    initialize_database(db_path)  # must not raise or duplicate rows

    conn = get_connection(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
    finally:
        conn.close()

    assert count == len(DEFAULT_CATEGORIES)


def test_seeds_default_categories(db_path):
    initialize_database(db_path)
    conn = get_connection(db_path)
    try:
        names = {
            row["name"]
            for row in conn.execute("SELECT name FROM categories").fetchall()
        }
    finally:
        conn.close()

    assert names == set(DEFAULT_CATEGORIES)


def test_seeds_singleton_settings_and_app_state(db_path):
    initialize_database(db_path)
    conn = get_connection(db_path)
    try:
        settings_row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        app_state_row = conn.execute("SELECT * FROM app_state WHERE id = 1").fetchone()
    finally:
        conn.close()

    assert settings_row is not None
    assert app_state_row is not None
    assert app_state_row["last_known_date"] is None


def test_foreign_keys_enforced(db_path):
    initialize_database(db_path)
    conn = get_connection(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO tasks
                    (title, task_type, category, importance, urgency,
                     seriousness, effort, created_at)
                VALUES ('Bad', 'normal', 'NoSuchCategory', 3, 3, 3, 2, '2026-01-01')
                """
            )
    finally:
        conn.close()


# --- Phase 5/6: additive column migrations for a pre-existing DB ---

def test_migration_adds_new_columns_to_a_pre_existing_database(db_path):
    """Simulates a real user's %APPDATA% DB created before Phase 5/6 —
    build the *old*-shaped tables by hand, then confirm initialize_database
    adds the new columns (with sensible defaults) rather than erroring on
    the already-existing tables."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            daily_capacities TEXT NOT NULL,
            utilization_target REAL NOT NULL,
            priority_weights TEXT NOT NULL,
            notifications_enabled INTEGER NOT NULL DEFAULT 1,
            sunday_reminder_enabled INTEGER NOT NULL DEFAULT 1,
            week_starts_monday INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    conn.execute(
        "INSERT INTO projects (name, description, active) VALUES ('Old Project', '', 1)"
    )
    conn.execute(
        "INSERT INTO settings (id, daily_capacities, utilization_target, priority_weights) "
        "VALUES (1, '[]', 0.75, '{}')"
    )
    conn.commit()
    conn.close()

    initialize_database(db_path)  # must not raise despite tables already existing

    conn = get_connection(db_path)
    try:
        project_row = conn.execute("SELECT * FROM projects WHERE name = 'Old Project'").fetchone()
        settings_row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    finally:
        conn.close()

    assert project_row["due_date"] is None  # pre-existing row untouched, new column defaults to NULL
    assert settings_row["week_gen_aggressiveness"] == "standard"
    assert settings_row["week_gen_weekend_allowed"] == 1
    assert settings_row["week_gen_allow_low_priority_automove"] == 1
    assert settings_row["theme_preference"] == "system"


def test_due_date_before_available_from_rejected(db_path):
    initialize_database(db_path)
    conn = get_connection(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO tasks
                    (title, task_type, category, importance, urgency,
                     seriousness, effort, available_from, due_date, created_at)
                VALUES ('Bad', 'normal', 'Personal', 3, 3, 3, 2,
                        '2026-01-10', '2026-01-01', '2026-01-01')
                """
            )
    finally:
        conn.close()
