# Architecture

## Module structure

```
app/
├── main.py                  entry point, startup sequence
├── config/settings.py       tunable constants, defaults
├── database/                sqlite3 connection + schema + repositories
│   ├── db.py
│   ├── schema.py
│   └── repositories/        one repository per table, no business logic
├── models/                  plain dataclasses mirroring the schema
├── core/                    pure, testable business logic
│   ├── priority_engine.py
│   ├── scheduling_engine.py
│   ├── state_engine.py      color derivation + rollover reconciliation
│   ├── recurrence_engine.py
│   └── date_service.py
├── notifications/           NotificationService abstraction (OS isolated here)
├── ui/                      PySide6 widgets — no business logic
├── services/                orchestration layer between UI and core/database
└── tests/
```

## Layering rule

UI → services → core / database(repositories)

UI widgets never call repositories or core engines directly. Business logic
never imports PySide6.

## Data flow

TODO: fill in once the vertical slice (SQLite → task creation → priority
calculation → scheduling → week view → complete/defer → state transitions)
is working end to end.

## Database

See `database/schema.py` for DDL. Minimum tables: tasks, projects,
task_schedule, fixed_events, recurrence_rules, weekly_history, categories,
settings, app_state.

Color is never stored as authoritative state — it's derived at read time
by `core/state_engine.py`.
