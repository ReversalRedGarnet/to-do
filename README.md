# Personal Adaptive Weekly Task Planner

A local-only desktop application for personal task management and weekly
planning. Not a conventional to-do list, not a calendar.

You enter tasks and obligations; the app evaluates them against urgency,
importance, consequence, deadline pressure, effort, and project relationships,
and distributes them across the days of the week — not exact times.

**Status:** vertical slice working end to end (task creation, priority
scoring, weekly scheduling, week/today views, complete/defer, color
state, multi-day rollover reconciliation) plus real Windows toast
notifications (winotify), a mid-session midnight-rollover timer,
recurring tasks (daily/weekly/monthly/custom-weekdays, editable from the
task editor), keyboard shortcuts (§50), system-aware dark mode, and a
packaged Windows build (see below) — 105/105 tests passing. A Settings
screen is not wired up yet. See `IMPLEMENTATION_PLAN.md` for the
phase-by-phase status and `ARCHITECTURE.md` / `ALGORITHM.md` for design
details.

## Running

```
pip install -r requirements.txt
python -m app.main
```

## Testing

```
pytest
```

## Building the Windows executable

```
pyinstaller TaskPlanner.spec
```

Produces `dist/TaskPlanner/TaskPlanner.exe` plus its `_internal/`
dependencies (a onedir build — faster startup than onefile, which
re-extracts everything to a temp dir on every launch). Note: build the
`.exe` on an actual Windows machine — cross-compiling from another OS is
unreliable. The app's data directory (`%APPDATA%/TaskPlanner/`) is
identical whether running frozen or via `python -m app.main` — verified
empirically by writing a task from one and reading it back from the
other, not just by inspecting `default_db_path()`'s source.

## Project layout

See `ARCHITECTURE.md`.

## Scope

Single-user, offline, no accounts, no cloud sync, no analytics/streaks/
gamification. See the full specification for details on what's explicitly
out of scope.
