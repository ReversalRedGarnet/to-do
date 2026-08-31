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
pyinstaller --name TaskPlanner --windowed app/main.py
```

Build the Windows `.exe` on an actual Windows machine. Before relying on
notifications in the packaged build, confirm the chosen toast library
(winotify or win11toast) actually fires from a frozen exe — this was
flagged as a Phase 1 spike for exactly this reason.

## Logging

Use the standard `logging` module. Logs are for debugging, not a
user-facing history feature — don't let this turn into analytics.
