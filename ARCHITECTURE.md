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
│   ├── title_parser.py      task-editor title auto-fill hints
│   ├── quick_entry_parser.py  quick-add shorthand ("category: due <when>: title")
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
7. `QuickTaskEntry` (`ui/task_entry.py`) also accepts a colon-delimited
   shorthand, `"<category>: due <when>: <title>"` (e.g. `"work: due
   today: submit form"`), parsed by the pure `core/quick_entry_parser.py`
   before the same `TaskService.create_task` call — a plain-text title
   with no colons is always still accepted. Any due date this produces
   (or any due date entered anywhere else, including the task editor)
   that lands in the past is clamped forward to today by
   `core.date_service.normalize_due_date`, applied once inside
   `TaskService.create_task`/`update_task` so no entry point can bypass
   it.
8. Opening the app, and switching the sidebar to This Week, calls
   `WeeklyBoard.scroll_to_first_active_day()` (`ui/weekly_board.py`) —
   a pure scroll-position adjustment, never touching what's scheduled: if
   today has no scheduled tasks but a later day this week does, the view
   jumps to that day.

## Database

See `database/schema.py` for DDL. Minimum tables: tasks, projects,
task_schedule, fixed_events, recurrence_rules, weekly_history, categories,
settings, app_state, schema_version. `categories` is seeded from
`config.settings.DEFAULT_CATEGORIES` — fixed at Family, Personal, Work,
School, Health. A task carries only a `due_date`; there is no
"available from"/start-date concept.

`database/db.py` runs two independent migration mechanisms against every
real `%APPDATA%` database on every startup, in addition to fixture/test
databases going through the same `initialize_database()` entry point:
- `_MIGRATIONS` — additive-only `ALTER TABLE ... ADD COLUMN`, gated
  simply on whether the column already exists (no version tracking
  needed, since that check is itself idempotent).
- `_VERSIONED_MIGRATIONS` — for changes a plain `ADD COLUMN` can't
  express (e.g. dropping a column), gated on the singleton
  `schema_version` row: build a new table matching the current schema,
  copy the surviving columns' data across inside one transaction, drop
  the old table, rename the new one into place, then bump the recorded
  version. `_drop_tasks_available_from_column` (version 1) is the first
  and so far only entry.

Color is never stored as authoritative state — it's derived at read time
by `core/state_engine.py`.
