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
        _seed_defaults(conn)
        conn.commit()
    finally:
        conn.close()


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
