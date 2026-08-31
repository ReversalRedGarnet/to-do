# Development

## Environment setup

```
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## Running the app

```
python -m app.main
```

## Tests

```
pytest
```

Run tests after every major subsystem (priority engine, scheduler, state
engine/rollover) before moving on. Notification tests must mock
`NotificationService` — never fire real OS notifications in the suite.

## Debugging the scheduler

`core/scheduling_engine.py` should expose enough intermediate data
(priority score, deadline pressure, eligible dates, chosen date, reason,
capacity consumed) to answer "why was this task placed here" — see
spec §36-37. Surface this via logging or a debug view, not necessarily
in the production UI.

## Packaging

```
pyinstaller TaskPlanner.spec
```

Onedir build (`dist/TaskPlanner/TaskPlanner.exe` + `_internal/`) — chosen
over onefile since a Qt app's onefile mode re-extracts everything to a
temp dir on every launch, a noticeably slower startup for no real
portability benefit here. Build the Windows `.exe` on an actual Windows
machine.

`winotify` (the toast library, chosen in the Phase 1 spike) and
`default_db_path()`'s `%APPDATA%` resolution were both re-verified
against the actual frozen build, not assumed to still work post-freeze:
the frozen exe was launched for real, confirmed it read/wrote the same
`%APPDATA%/TaskPlanner/task_planner.db` as an unfrozen `python -m
app.main` run (a task written by one was visible to the other — ruling
out the classic `sys.executable`-vs-`__file__` PyInstaller path trap),
and the toast fired and was visually confirmed.

## Logging

Use the standard `logging` module. Logs are for debugging, not a
user-facing history feature — don't let this turn into analytics.
