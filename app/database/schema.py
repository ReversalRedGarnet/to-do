"""
DDL for the application's SQLite schema.

Minimum required tables (see spec / ARCHITECTURE.md):
    tasks, projects, task_schedule, fixed_events,
    recurrence_rules, weekly_history, categories, settings, app_state

app_state holds a single row tracking last_known_date for rollover
reconciliation (see core/date_service.py and core/state_engine.py).

Dates are stored as ISO-8601 strings (YYYY-MM-DD) — see core/date_service.py
for the single source of truth on date semantics. Booleans are stored as
INTEGER 0/1 (sqlite3 has no native boolean type).
"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS recurrence_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    frequency  TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly', 'custom_weekdays')),
    interval   INTEGER NOT NULL DEFAULT 1 CHECK (interval >= 1),
    weekdays   TEXT,       -- comma-separated 0=Mon..6=Sun, only for custom_weekdays
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
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

    available_from TEXT,   -- ISO date, nullable
    due_date        TEXT,   -- ISO date, nullable

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

    CHECK (available_from IS NULL OR due_date IS NULL OR available_from <= due_date),
    CHECK (NOT (completed_at IS NOT NULL AND deferred_at IS NOT NULL AND status != 'completed'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);

CREATE TABLE IF NOT EXISTS fixed_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    event_date   TEXT NOT NULL,   -- ISO date, never moved by the scheduler
    event_time   TEXT,            -- optional HH:MM, informational only
    category     TEXT REFERENCES categories(name) ON UPDATE CASCADE,
    capacity_cost INTEGER NOT NULL DEFAULT 0 CHECK (capacity_cost >= 0)
);

CREATE INDEX IF NOT EXISTS idx_fixed_events_date ON fixed_events(event_date);

CREATE TABLE IF NOT EXISTS task_schedule (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id          INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    week_start       TEXT NOT NULL,  -- ISO date of the Monday
    scheduled_date   TEXT NOT NULL,  -- ISO date within that week
    schedule_reason  TEXT NOT NULL,
    manual_override  INTEGER NOT NULL DEFAULT 0 CHECK (manual_override IN (0, 1)),
    locked           INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
    UNIQUE (task_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_task_schedule_week ON task_schedule(week_start);
CREATE INDEX IF NOT EXISTS idx_task_schedule_date ON task_schedule(scheduled_date);

CREATE TABLE IF NOT EXISTS weekly_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start    TEXT NOT NULL UNIQUE,
    week_end      TEXT NOT NULL,
    snapshot_json TEXT NOT NULL  -- completed/missed/deferred task ids, see services/history_service.py
);

CREATE TABLE IF NOT EXISTS settings (
    id                       INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    daily_capacities         TEXT NOT NULL,  -- JSON list of 7 capacity names, Monday-first
    utilization_target       REAL NOT NULL,
    priority_weights         TEXT NOT NULL,  -- JSON object
    notifications_enabled    INTEGER NOT NULL DEFAULT 1 CHECK (notifications_enabled IN (0, 1)),
    sunday_reminder_enabled  INTEGER NOT NULL DEFAULT 1 CHECK (sunday_reminder_enabled IN (0, 1)),
    week_starts_monday       INTEGER NOT NULL DEFAULT 1 CHECK (week_starts_monday IN (0, 1))
);

CREATE TABLE IF NOT EXISTS app_state (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    last_known_date      TEXT,  -- ISO date; NULL until the first reconciliation pass completes
    last_notified_date   TEXT   -- ISO date of the last startup/rollover notification batch,
                                 -- so the startup pass and the mid-session timer can't both
                                 -- fire the same day's notifications (spec §31 "avoid excessive")
);
"""
