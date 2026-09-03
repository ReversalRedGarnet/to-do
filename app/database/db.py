"""
SQLite connection management.

Keep this thin: plain sqlite3, one connection helper, schema application.
Do not introduce an ORM unless plain sqlite3 genuinely becomes unwieldy.
"""

import json
import os
import sqlite3
from pathlib import Path

from app.config.settings import (
    APP_NAME,
    DATABASE_FILENAME,
    DEFAULT_CATEGORIES,
    DEFAULT_WEEKLY_CAPACITY,
    PRIORITY_WEIGHTS,
    UTILIZATION_TARGET,
)
from app.database.schema import SCHEMA_SQL


def default_db_path() -> Path:
    """Per-user app data directory: %APPDATA% on Windows, ~/.local/share
    elsewhere (only Windows is a packaging target — see DEVELOPMENT.md)."""
    base = os.environ.get("APPDATA")
    app_dir = Path(base) / APP_NAME if base else Path.home() / f".{APP_NAME.lower()}"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / DATABASE_FILENAME


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with sensible defaults (foreign keys on)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: Path) -> None:
    """Create tables if they do not already exist, then seed first-run
    defaults (categories, singleton settings/app_state rows) if missing."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        _apply_versioned_migrations(conn)
        _apply_migrations(conn)
        _seed_defaults(conn)
        conn.commit()
    finally:
        conn.close()


# --- Versioned migrations (table rebuilds — see schema_version in
# schema.py) ---
#
# SQLite's DROP COLUMN support depends on the SQLite version bundled with
# the running Python (only 3.35.0+, and even then it can't drop a column
# referenced by an index/CHECK/generated column, which `available_from`
# was), so this uses the universally-safe rebuild pattern instead: build
# a new table matching the current schema, copy every remaining column's
# data across inside a transaction, drop the old table, and rename the
# new one into place. Each migration is a no-op if its target shape is
# already in place (fresh installs included), so re-running
# initialize_database is always safe.


def _drop_tasks_available_from_column(conn: sqlite3.Connection) -> None:
    """Removes `tasks.available_from`, left over from before it was
    dropped from SCHEMA_SQL (the task no longer has a start-date concept,
    only `due_date`)."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "available_from" not in columns:
        return  # fresh install, or a DB that's already been migrated

    # Take manual control of transactions/pragmas for this rebuild rather
    # than relying on sqlite3's implicit-transaction heuristics — PRAGMA
    # foreign_keys can only be changed outside a transaction, and we need
    # a single all-or-nothing transaction around the rebuild itself.
    previous_isolation_level = conn.isolation_level
    conn.commit()  # flush anything left pending before taking manual control
    conn.isolation_level = None
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            conn.execute(
                """
                CREATE TABLE tasks_new (
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

                    CHECK (NOT (completed_at IS NOT NULL AND deferred_at IS NOT NULL AND status != 'completed'))
                )
                """
            )
            conn.execute(
                """
                INSERT INTO tasks_new
                    (id, project_id, title, description, task_type, category,
                     importance, urgency, seriousness, effort, due_date,
                     status, progress, created_at, completed_at, deferred_at,
                     last_scheduled_date, current_scheduled_date,
                     days_exposed, times_deferred, times_ignored,
                     recurrence_rule_id, created_week)
                SELECT
                    id, project_id, title, description, task_type, category,
                    importance, urgency, seriousness, effort, due_date,
                    status, progress, created_at, completed_at, deferred_at,
                    last_scheduled_date, current_scheduled_date,
                    days_exposed, times_deferred, times_ignored,
                    recurrence_rule_id, created_week
                FROM tasks
                """
            )
            conn.execute("DROP TABLE tasks")
            conn.execute("ALTER TABLE tasks_new RENAME TO tasks")
            # DROP TABLE also drops its indexes — recreate them under the
            # same names schema.py uses so the on-disk shape matches a
            # fresh install exactly.
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")

            violations = conn.execute("PRAGMA foreign_key_check(tasks)").fetchall()
            if violations:
                raise sqlite3.IntegrityError(
                    f"available_from migration produced {len(violations)} foreign key "
                    "violation(s) on tasks — rolling back"
                )

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.isolation_level = previous_isolation_level


# (version, migration_fn) pairs, applied in order to any database whose
# recorded `schema_version.version` is below that version. Never remove,
# reorder, or renumber entries here; only append with the next integer.
_VERSIONED_MIGRATIONS = [
    (1, _drop_tasks_available_from_column),
]


def _apply_versioned_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, 0)")
    conn.commit()
    current = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()["version"]
    for version, migration in _VERSIONED_MIGRATIONS:
        if current < version:
            migration(conn)
            conn.execute("UPDATE schema_version SET version = ? WHERE id = 1", (version,))
            conn.commit()
            current = version


# Additive-only, idempotent column migrations for a real user's existing
# %APPDATA% database — `CREATE TABLE IF NOT EXISTS` alone can't add a
# column to a table that already exists from an earlier version. Each
# entry is (table, column, "ADD COLUMN" DDL fragment after the column
# name). Never remove or reorder entries here; only append.
_MIGRATIONS = [
    ("projects", "due_date", "TEXT"),
    ("settings", "week_gen_aggressiveness",
     "TEXT NOT NULL DEFAULT 'standard' CHECK (week_gen_aggressiveness IN ('relaxed', 'standard', 'aggressive'))"),
    ("settings", "week_gen_weekend_allowed",
     "INTEGER NOT NULL DEFAULT 1 CHECK (week_gen_weekend_allowed IN (0, 1))"),
    ("settings", "week_gen_allow_low_priority_automove",
     "INTEGER NOT NULL DEFAULT 1 CHECK (week_gen_allow_low_priority_automove IN (0, 1))"),
    ("settings", "theme_preference",
     "TEXT NOT NULL DEFAULT 'system' CHECK (theme_preference IN ('system', 'light', 'dark'))"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, column, ddl in _MIGRATIONS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _seed_defaults(conn: sqlite3.Connection) -> None:
    for name in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,)
        )

    conn.execute(
        """
        INSERT OR IGNORE INTO settings
            (id, daily_capacities, utilization_target, priority_weights,
             notifications_enabled, sunday_reminder_enabled, week_starts_monday)
        VALUES (1, ?, ?, ?, 1, 1, 1)
        """,
        (
            json.dumps([c.name for c in DEFAULT_WEEKLY_CAPACITY]),
            UTILIZATION_TARGET,
            json.dumps(PRIORITY_WEIGHTS),
        ),
    )

    conn.execute(
        "INSERT OR IGNORE INTO app_state (id, last_known_date) VALUES (1, NULL)"
    )
