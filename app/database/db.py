"""
SQLite connection management.

Keep this thin: plain sqlite3, one connection helper, schema application.
Do not introduce an ORM unless plain sqlite3 genuinely becomes unwieldy.
"""

import sqlite3
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with sensible defaults (foreign keys on)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: Path) -> None:
    """Create tables if they do not already exist. See schema.py."""
    raise NotImplementedError("Apply schema.py's DDL against get_connection(db_path).")
