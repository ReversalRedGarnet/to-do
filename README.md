# Personal Adaptive Weekly Task Planner

A local-only desktop application for personal task management and weekly
planning. Not a conventional to-do list, not a calendar.

You enter tasks and obligations; the app evaluates them against urgency,
importance, consequence, deadline pressure, effort, and project relationships,
and distributes them across the days of the week — not exact times.

**Status:** skeleton / not yet implemented. See `IMPLEMENTATION_PLAN.md`
(generated once implementation starts) and `ARCHITECTURE.md` / `ALGORITHM.md`
below for design details.

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
pyinstaller --name TaskPlanner --windowed app/main.py
```

Note: build the `.exe` on an actual Windows machine — cross-compiling from
another OS is unreliable.

## Project layout

See `ARCHITECTURE.md`.

## Scope

Single-user, offline, no accounts, no cloud sync, no analytics/streaks/
gamification. See the full specification for details on what's explicitly
out of scope.
