"""
DDL for the application's SQLite schema.

Minimum required tables (see spec / ARCHITECTURE.md):
    tasks, projects, task_schedule, fixed_events,
    recurrence_rules, weekly_history, categories, settings, app_state

app_state holds a single row tracking last_known_date for rollover
reconciliation (see core/date_service.py and core/state_engine.py).

Fill in full CREATE TABLE statements here. Keep constraints (NOT NULL,
CHECK, FOREIGN KEY) meaningful — see spec §52 Data Integrity.
"""

SCHEMA_SQL = """
-- TODO: categories, projects, tasks, task_schedule, fixed_events,
-- recurrence_rules, weekly_history, settings, app_state.
"""
