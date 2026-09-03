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


# --- Versioned table-rebuild migration: dropping tasks.available_from ---

def _create_old_shaped_tasks_db(db_path) -> None:
    """Builds a DB matching the real pre-removal shape: `tasks.
    available_from` (with its old CHECK constraint), plus the tables it
    references/is referenced by, so the rebuild migration has real
    foreign-key relationships to preserve."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE categories (name TEXT PRIMARY KEY);

        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            due_date TEXT
        );

        CREATE TABLE recurrence_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frequency TEXT NOT NULL,
            interval INTEGER NOT NULL DEFAULT 1,
            weekdays TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            task_type   TEXT NOT NULL CHECK (task_type IN ('normal', 'project_child', 'fixed_event', 'recurring')),
            category    TEXT NOT NULL REFERENCES categories(name) ON UPDATE CASCADE,
            importance  INTEGER NOT NULL CHECK (importance BETWEEN 1 AND 5),
            urgency     INTEGER NOT NULL CHECK (urgency BETWEEN 1 AND 5),
            seriousness INTEGER NOT NULL CHECK (seriousness BETWEEN 1 AND 5),
            effort      INTEGER NOT NULL CHECK (effort BETWEEN 1 AND 5),
            available_from TEXT,
            due_date        TEXT,
            status   TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'scheduled', 'completed', 'deferred', 'cancelled')),
            progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
            created_at   TEXT NOT NULL,
            completed_at TEXT,
            deferred_at  TEXT,
            last_scheduled_date    TEXT,
            current_scheduled_date TEXT,
            days_exposed   INTEGER NOT NULL DEFAULT 0,
            times_deferred INTEGER NOT NULL DEFAULT 0,
            times_ignored  INTEGER NOT NULL DEFAULT 0,
            recurrence_rule_id INTEGER REFERENCES recurrence_rules(id) ON DELETE SET NULL,
            created_week        TEXT,
            CHECK (available_from IS NULL OR due_date IS NULL OR available_from <= due_date)
        );

        CREATE TABLE task_schedule (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id          INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            week_start       TEXT NOT NULL,
            scheduled_date   TEXT NOT NULL,
            schedule_reason  TEXT NOT NULL,
            manual_override  INTEGER NOT NULL DEFAULT 0,
            locked           INTEGER NOT NULL DEFAULT 0,
            UNIQUE (task_id, week_start)
        );
        """
    )
    conn.execute("INSERT INTO categories (name) VALUES ('Personal')")
    conn.execute(
        """
        INSERT INTO tasks
            (id, title, description, task_type, category, importance, urgency,
             seriousness, effort, available_from, due_date, status, progress,
             created_at, days_exposed, times_deferred, times_ignored)
        VALUES
            (1, 'Old task', 'a description', 'normal', 'Personal', 3, 4, 2, 3,
             '2026-01-01', '2026-01-10', 'pending', 0, '2026-01-01', 0, 0, 0)
        """
    )
    conn.execute(
        "INSERT INTO task_schedule (task_id, week_start, scheduled_date, schedule_reason) "
        "VALUES (1, '2026-01-05', '2026-01-06', 'TEST')"
    )
    conn.commit()
    conn.close()


def test_migration_drops_available_from_column_and_preserves_data(db_path):
    """Simulates a real %APPDATA% DB from before available_from was
    removed from SCHEMA_SQL: builds the old-shaped `tasks` table by hand
    (including the column, its CHECK constraint, and real data), then
    confirms initialize_database's versioned migration drops the column
    via the safe rebuild pattern while every other column's data — and
    the task_schedule row's foreign key to it — survives intact."""
    _create_old_shaped_tasks_db(db_path)

    conn = sqlite3.connect(db_path)
    old_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    conn.close()
    assert "available_from" in old_columns  # sanity check on the fixture itself

    initialize_database(db_path)

    conn = get_connection(db_path)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        assert "available_from" not in columns

        task_row = conn.execute("SELECT * FROM tasks WHERE id = 1").fetchone()
        assert task_row["title"] == "Old task"
        assert task_row["description"] == "a description"
        assert task_row["category"] == "Personal"
        assert task_row["importance"] == 3
        assert task_row["urgency"] == 4
        assert task_row["seriousness"] == 2
        assert task_row["effort"] == 3
        assert task_row["due_date"] == "2026-01-10"
        assert task_row["status"] == "pending"
        assert task_row["created_at"] == "2026-01-01"

        schedule_row = conn.execute(
            "SELECT * FROM task_schedule WHERE task_id = 1"
        ).fetchone()
        assert schedule_row is not None  # the FK relationship survived the rebuild
        assert schedule_row["scheduled_date"] == "2026-01-06"

        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        version_row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
        assert version_row["version"] >= 1
    finally:
        conn.close()

    initialize_database(db_path)  # re-running post-migration must not raise or redo the rebuild


def test_migration_is_a_no_op_on_a_fresh_database(db_path):
    """A brand-new database created against the current SCHEMA_SQL never
    had `available_from` at all — the versioned migration must detect
    that (rather than erroring on the missing column) and just record the
    schema as already up to date."""
    initialize_database(db_path)

    conn = get_connection(db_path)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        version_row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    finally:
        conn.close()

    assert "available_from" not in columns
    assert version_row["version"] >= 1
