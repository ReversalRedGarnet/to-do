# Implementation Plan — Personal Adaptive Weekly Task Planner

Reflects spec §61 phase order, amended per the brief's §2(a-e). This file
is a living index of progress — checkboxes get ticked as work lands, not
rewritten wholesale.

## Confirmed scope decisions (per brief §2.e)

- **Phases 1-6 are the real product** and will be built to full test
  coverage before anything else: foundation, data model, basic GUI,
  priority engine, scheduling engine, state engine.
- **Phases 7-10** (notifications beyond the go/no-go spike, packaging,
  dark mode, polish) are explicitly separable and may slip without
  blocking a usable v1.
- The **vertical slice (§65)** comes first, inside Phases 1-6: SQLite
  schema → task creation → priority engine → one-week greedy scheduler →
  week view → complete/defer → state transitions, fully tested, before
  projects, recurrence, history cleanup, or notifications get built out.
- Scheduler is a **greedy allocator, not an optimizer**: sort by priority
  descending, walk Monday→Sunday, place each task on the earliest in-window
  day with room under `UTILIZATION_TARGET`, else place on the day with
  most in-window slack and flag `OVERCOMMITTED`. No backtracking, no
  lookahead, no fairness reshuffling — that's v2.
- Constants in `app/config/settings.py` are final for v1 and will not be
  re-tuned during this pass.
- Windows notification spike (winotify/win11toast, from a PyInstaller-frozen
  exe) happens early in Phase 1 as a throwaway go/no-go check, separate
  from the real `NotificationService` (Phase 7).
- Phase 10 (PyInstaller Windows .exe) will be flagged back rather than
  guessed at if this environment turns out not to be a real Windows
  machine capable of producing a native build.

## Phase 1 — Foundation

- [x] Confirm venv/dependencies installable (existing `.venv` already has
      PySide6, pytest, PyInstaller; `winotify` added after the spike below)
- [x] `app/database/schema.py` — full DDL: categories, projects, tasks,
      task_schedule, fixed_events, recurrence_rules, weekly_history,
      settings, app_state (last_known_date)
- [x] `app/database/db.py` — `initialize_database()` applies schema,
      seeds default categories/singleton settings+app_state rows,
      `default_db_path()` resolves `%APPDATA%/TaskPlanner/`
- [x] Logging setup (`app/logging_config.py`, stdlib `logging`, file +
      stream handler, not user-facing history)
- [x] Basic smoke tests: `app/tests/test_database.py` — schema creates all
      tables, idempotent re-init, default seeding, FK + CHECK constraints
      enforced (6/6 passing)
- [x] **Notification spike (throwaway):** `scripts/notification_spike.py`,
      built with PyInstaller (`--onefile`) and run as a real frozen exe on
      this Windows machine. **Result: PASS** — `winotify` fires without
      raising both unfrozen and frozen. Chosen as the library; `.venv`
      already has it, `requirements.txt` updated. *(I couldn't visually
      confirm the toast rendered — please confirm you saw it pop up when
      you ran it, since "didn't raise" isn't proof it displayed.)*

## Phase 2 — Data model

- [x] Repositories: `TaskRepository`, `ProjectRepository`,
      `ScheduleRepository`, `FixedEventRepository`, `HistoryRepository`,
      `CategoryRepository`, `SettingsRepository`, `AppStateRepository`
      (`RecurrenceRepository` deferred — recurrence stays Phase 8)
- [x] CRUD wired against schema; data-integrity constraints from spec §52
      enforced at the DB layer (CHECK constraints, FKs) — verified in
      `test_database.py`
- [x] Added `app/models/fixed_event.py` (schema had a `fixed_events` table
      and `generate_weekly_schedule` already took a separate `fixed_events`
      param, but no domain dataclass existed yet — filled the gap)

## Phase 3 — Basic GUI

- [x] `ui/main_window.py` — QMainWindow, sidebar (Today / This Week /
      Projects), stacked content. **Settings is not in the sidebar** —
      left out rather than added as a non-functional placeholder; full
      settings editing is still Phase 8/9 scope.
- [x] Today view (quick-add + today's board), Week view (day columns,
      Generate Week button, Complete/Defer/Edit per card)
- [x] Task creation (`task_entry.py`) and full editing (`task_editor.py`)
      wired to `services/task_service.py` — every control works
- [x] `ui/project_view.py` — active projects, progress bar, next
      actionable child (spec §41)
- [x] Driven end-to-end with a Qt/QTest script against a throwaway DB:
      launched, quick-added a task, generated the week, confirmed the
      card's color stripe (YELLOW, pixel-verified `#f9a825`), clicked
      Complete (stripe correctly dropped to neutral gray, Complete/Defer
      buttons correctly disappeared), viewed Projects. Two real bugs
      found and fixed this way: completed tasks still showed
      Complete/Defer buttons, and card text was being clipped by
      side-by-side buttons (moved buttons to a row below the text).

## Phase 4 — Priority engine

- [x] Filled in `core/priority_engine.py`: all component functions plus
      `calculate_priority_score` combining via `PRIORITY_WEIGHTS`
- [x] `app/tests/test_priority.py` — all 5 stubbed cases + due-date edge
      cases (7/7 passing)
- [ ] Dedicated debug explanation view (score breakdown) — not built;
      the underlying data (score, deadline pressure) is trivially
      available via the engine functions, just not surfaced in a UI yet

## Phase 5 — Scheduling engine

- [x] Filled in `core/scheduling_engine.py`: `generate_weekly_schedule`
      (greedy allocator exactly as specified) and
      `rebalance_after_missed_task` (recovery helper — pushes the
      lightest existing placement forward by one day to make room rather
      than piling onto the target day, spec §39)
- [x] `app/tests/test_scheduling.py` — all 7 stubbed cases (8/8 passing,
      incl. fixed-event capacity consumption)

## Phase 6 — State engine (vertical slice's hardest part)

- [x] `core/state_engine.derive_color` — pure function, task + today +
      schedule context → Color (+ `derive_project_color()` for the
      always-PURPLE project case)
- [x] `core/state_engine.reconcile(last_known_date, today, db_state)`:
      replay day-by-day **inclusive of `last_known_date`** (a day the app
      confirmed as "today" may never have been closed if the app quit
      before its own midnight rollover — see the docstring/comment in
      the code), exclusive of `today` itself; missed-task marking,
      orange/red transitions, week-boundary archive+purge all verified.
      `last_known_date` persisted only after the pass completes.
- [x] `app/tests/test_rollover.py` — gaps of 0, 1, 5, 10+ days, single and
      double week-boundary crossings (7/7 passing)
- [x] `app/tests/test_state_transitions.py` — orange/red/defer/green/
      fixed-event/yellow cases (8/8 passing)
- [x] `main.py` startup sequence fully wired: init db → build db_state
      from repositories across the reconciled date range
      (`ScheduleService.get_task_ids_between`) → `reconcile()` → persist
      mutated tasks + archived weeks → `set_last_known_date` → build and
      show the main window. Real `WindowsNotificationService` intentionally
      not wired yet — `NullNotificationService` is used (Phase 7 scope).

**End of vertical slice — full pytest run passes (46/46) — confirmed working
end-to-end via the driven UI session above.**

## Phase 7 — Notifications (separable, may slip)

- [x] Go/no-go spike passed (Phase 1), **visually confirmed by the user**
      on a real frozen exe — not just "didn't raise"
- [x] Real `WindowsNotificationService` (`app/notifications/notification_service.py`)
      using `winotify`, wired into `main.py` in place of `NullNotificationService`.
      Reads `notifications_enabled` from the settings row on every call
      (not cached at construction) and swallows+logs any failure so a
      broken toast backend can never crash the app.
- [x] Extended the `NotificationService` ABC with one new method,
      `notify_missed_tasks(missed_tasks)` — spec §33 lists
      notify_task/notify_event/notify_weekly_plan_required/notify_day_rollover
      as "methods such as", not an exhaustive interface, and firing
      `notify_task` once per missed task after a multi-day gap would be
      exactly the spam spec §31 warns against. 1 missed task -> single
      "You didn't complete: X"; 2+ -> one summary toast, titles capped at 3.
- [x] `app/services/reconciliation_service.py` — extracted the
      replay-and-persist logic out of `main.py` so both the startup path
      and the new mid-session rollover timer share one implementation.
- [x] `main._send_startup_notifications` — the startup batch: missed-task
      summary, weekly plan reminder (fires from Sunday onward per
      `_PLANNING_REMINDER_WEEKDAY`, gated on `sunday_reminder_enabled`),
      today's fixed events, and the single highest-priority task due/
      expected today. Guarded by a new `app_state.last_notified_date`
      column so relaunching the app the same day, or the mid-session
      timer catching up later, can't double-fire.
- [x] Mid-session rollover timer (`ui/main_window._install_rollover_timer`),
      interval pinned to `config.settings.ROLLOVER_CHECK_INTERVAL_SECONDS`
      (5 min) per your amendment — detects the date advancing while the
      app stays open (spec §19), re-runs `ReconciliationService`, refreshes
      all three panels in place, and fires exactly one `notify_day_rollover`
      — **never** the startup batch, per your second amendment (avoids
      double-firing after a multi-day gap).
- [x] Tests: `test_notifications.py` (8, winotify monkeypatched — disabled
      setting, wording, missed-task summarization, broken-backend
      swallowing), `test_reconciliation_service.py` (3), `test_startup_notifications.py`
      (10, covering the Sunday/disabled/already-planned/double-fire cases)
- [ ] A real Settings screen in the sidebar to edit `notifications_enabled`/
      `sunday_reminder_enabled` — still Phase 8/9 scope; the settings row
      exists and is read live, just not yet user-editable from the UI

## Phase 8 — Persistence / recovery polish

- [x] `services/history_service.py` — archive/purge, tested against
      `test_history.py` (6/6 passing), including
      `apply_reconciliation_archives` which persists `reconcile()`'s
      `weeks_archived` output
- [x] Projects (`test_projects.py`, 4/4 passing) — `TaskService.
      project_progress` / `next_actionable_item`, wired into
      `ProjectView`
- [x] Recurrence (spec §44): new `app/models/recurrence.py`
      (`RecurrenceRule`/`RecurrenceFrequency`) + `RecurrenceRepository`,
      filled in `core/recurrence_engine.generate_next_occurrence` (daily/
      weekly/monthly-with-month-end-clamping/custom-weekdays), and
      `services/recurrence_service.py` (`set_recurrence`,
      `clear_recurrence`, `ensure_next_occurrence`). Wired into
      `TaskService.complete_task`: completing a recurring task spawns the
      next occurrence as a **new** Task row via `create()` — the
      just-completed row is never mutated beyond its own COMPLETED
      status/`completed_at`, confirmed by
      `test_recurrence_service.py::test_completing_a_recurring_task_keeps_original_row_intact_and_spawns_next`.
      Usable through the app itself, not just seed data: `TaskEditorDialog`
      gained a "Repeats" frequency dropdown, an interval spinner, and
      weekday checkboxes for the custom case — covered end-to-end by
      `test_task_editor_recurrence.py` (constructs the real dialog widget,
      not a stand-in).
- [x] Schedule-consistency repair (spec §52 "corrupted/missing weekly
      schedule"): `ScheduleService.generate_week` persists `task_schedule`
      rows and then updates each task's status in separate commits — a
      crash between those two steps could strand a task marked SCHEDULED
      with no matching schedule row. `ReconciliationService.run` now
      detects and resets exactly that drift on every pass (startup and
      the mid-session timer), tested in `test_reconciliation_service.py`.
- [x] Tests: `test_recurrence.py` (10, pure engine math incl. month-end
      edge case), `test_recurrence_service.py` (4), `test_task_editor_recurrence.py`
      (5), plus 2 new `test_reconciliation_service.py` cases for the
      drift repair — 88/88 passing overall.

## Phase 9 — UX polish (separable, may slip)

- [x] Card selection model (`app/ui/widgets/task_selection_mixin.py` +
      `TaskCard.card_clicked`/`set_selected`): clicking a card highlights
      it with a blue outline distinct from the state-color stripe.
      Required groundwork for keyboard shortcuts — cards weren't
      selectable/focusable at all before this.
- [x] Keyboard shortcuts (spec §50): `Ctrl+N` focuses the active panel's
      quick-add, `Ctrl+W`/`Ctrl+T`/`Ctrl+P` switch views, `Ctrl+E`/`D`/
      `Delete`/`Enter` act on the selected task in whichever of Today/
      This Week is active (no-op on Projects, which has no selectable
      tasks). Per your two amendments: (1) all four act-on-selection
      shortcuts simply do nothing when nothing is selected — no
      fallback to "first card" (`test_nothing_selected_shortcuts_are_a_no_op`);
      (2) selection clears on view switch, wired into the sidebar's
      `currentRowChanged` handler so it fires the same way whether
      triggered by a mouse click or a `Ctrl+W/T/P` shortcut
      (`test_view_switch_clears_selection`). None of the shortcuts fire
      while a text field has focus (checked via `QApplication.focusWidget()`).
      **Enter's documented rule**: a pending/scheduled/deferred task is
      completed; an already-completed task opens its editor instead —
      see `TodayPanel.activate_selected`/`WeeklyBoard.activate_selected`'s
      docstrings and `test_activate_selected_opens_editor_for_completed_task`.
- [x] Dark mode (spec §49, "if practical"): `app/ui/theme.py` detects the
      OS color scheme via `QGuiApplication.styleHints().colorScheme()`
      (Qt 6.5+) and, only when dark, switches to the Fusion style with an
      explicit dark `QPalette` — the native Windows style doesn't repaint
      from a palette change alone. The six state colors are saturated
      border accents, not fills, so they stay legible unchanged in both
      modes — visually confirmed via screenshot (yellow stripe still
      reads clearly against the dark card background).
- [x] Explicitly skipped per spec: context menus (no spec requirement,
      every action already has a button) and drag-and-drop (spec calls
      it "desirable but not mandatory," and Defer/Move already are the
      required non-drag alternative).
- [x] Tests: `test_ui_selection_and_shortcuts.py` (10, panel-level
      selection/activate/defer/cancel logic against a real temp DB) and
      `test_shortcuts_and_theme.py` (7, drives the *real*
      `build_main_window` + `QShortcut`s via `QTest.keySequence`, plus the
      theme switch) — 105/105 passing overall. Modal dialogs
      (`TaskEditorDialog`, `_DeferDialog`) are monkeypatched to
      auto-accept in these tests so they don't block on a real event loop.

## Phase 10 — Packaging (separable, may slip)

- [x] This environment is confirmed to be a real Windows machine (the
      Phase 1 notification spike's frozen exe and toast both ran here),
      so packaging was never actually blocked — flagging that
      explicitly rather than assuming, per the original brief.
- [x] `TaskPlanner.spec` checked in at the repo root (onedir, chosen over
      onefile — a Qt onefile build re-extracts everything to a temp dir
      on every launch, a real startup-latency cost with no portability
      upside for this use case). `pyinstaller TaskPlanner.spec` builds
      `dist/TaskPlanner/TaskPlanner.exe` + `_internal/`.
- [x] `default_db_path()`'s `%APPDATA%` resolution was verified
      **empirically**, not assumed safe from reading the code (it has no
      `sys.executable`/`__file__` dependency, but that's exactly the kind
      of thing PyInstaller can surprise you on): built the spec, launched
      the frozen exe for real, confirmed it created
      `%APPDATA%/TaskPlanner/task_planner.db` fresh with the full schema
      and seeded categories — not a file next to the exe. Then wrote a
      task from the unfrozen `python -m app.main` dev process and
      confirmed the frozen exe's next launch saw it (and vice versa),
      proving both resolve to the identical store rather than two
      different databases.
- [x] Launched the final `--windowed` (no console) build and confirmed
      via `Get-Process` that a real "My Week" window opens with no
      console attached, plus a genuine desktop screenshot (not an
      in-process Qt render) showing the packaged app's window.
- [x] No asset bundling was needed — the app has no icons/fonts/data
      files beyond what PySide6/winotify's own PyInstaller hooks already
      handle automatically (confirmed by the clean build + clean run).

---

Progress is tracked by checking boxes above as each piece lands and tests
pass. See `ARCHITECTURE.md` for module boundaries, `ALGORITHM.md` for the
scoring/scheduling/color rules, `DEVELOPMENT.md` for environment/test/
packaging commands.
