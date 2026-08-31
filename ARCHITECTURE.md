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

The vertical slice works end to end. On startup (`app/main.py`):

1. `database.db.initialize_database` applies `schema.py`'s DDL and seeds
   default categories/settings/app_state rows if missing.
2. `core.date_service.today()` + `AppStateRepository.get_last_known_date()`
   feed `core.state_engine.reconcile()`. Its `db_state["schedule"]` is
   built by `ScheduleService.get_task_ids_between`, which spans however
   many weeks the gap covers (repositories are queried per-week, since
   `task_schedule` rows are stored keyed by `week_start`).
3. `reconcile()`'s mutated tasks are persisted back via
   `TaskRepository.update`; any `weeks_archived` entries are persisted via
   `HistoryService.apply_reconciliation_archives`; only then is
   `last_known_date` advanced to today.
4. `ui.main_window.build_main_window` wires `TaskService` / `ScheduleService`
   / repositories into the Today, This Week, and Projects panels. Every
   panel calls services only — never repositories or core engines directly.
5. Creating a task (`QuickTaskEntry` → `TaskService.create_task`) does not
   put it on any board by itself — a task only appears under a day once
   `ScheduleService.generate_week` (the "Generate Week" button) has run
   and produced `task_schedule` rows for it. This matches spec §45: the
   app never auto-schedules without the user asking it to.
6. Complete/Defer/Edit on a card call `TaskService` (task-level fields)
   and, for Defer/Move, `ScheduleService.move_task` (the persisted
   `task_schedule` row) together — see `ui/weekly_board.py`.

## Database

See `database/schema.py` for DDL. Minimum tables: tasks, projects,
task_schedule, fixed_events, recurrence_rules, weekly_history, categories,
settings, app_state.

Color is never stored as authoritative state — it's derived at read time
by `core/state_engine.py`.
