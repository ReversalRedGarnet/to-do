# Algorithm

## Constants (v1 — do not change without updating tests)

```
Effort units:        1→1, 2→2, 3→3, 4→5, 5→8   (super-linear)
Capacity:             LOW=3, MEDIUM=6, HIGH=9
Default week:         Mon–Fri MEDIUM, Sat HIGH, Sun LOW
Utilization target:   75%
Deadline horizon:     14 days
Orange threshold:     1 missed opportunity
Red threshold:        3 consecutive missed opportunities (eligible days only)
```

## Priority score

```
score = importance * 0.30
      + urgency * 0.20
      + seriousness * 0.25
      + deadline_pressure * 0.15
      + context_adjustment * 0.10
```

Each component is its own testable function in `core/priority_engine.py`.

## Deadline pressure

```
if no due date: 0
if days_remaining <= 0: 5 (max)
else: clamp(5 * (1 - days_remaining / 14), 0, 5)
```

## Scheduling (v1 — greedy allocator, not an optimizer)

1. Sort eligible tasks by priority score, descending.
2. Walk days Monday → Sunday; walk tasks in sorted order.
3. Place each task on the earliest day on/before its `due_date` (tasks
   with no due date are eligible on any day) with remaining capacity
   under the utilization target.
4. If no day in-window has room, place on the day with the most slack
   in-window anyway and flag `OVERCOMMITTED`.

No backtracking, no lookahead, no fairness reshuffling in v1. Load
balancing refinement is v2 scope.

## Color-state rules

| Color  | Meaning |
|--------|---------|
| GREEN  | Completed voluntarily/ahead of the day it was expected |
| YELLOW | Required attention today |
| ORANGE | Missed a prior reasonable opportunity (1+) |
| RED    | Repeatedly ignored (3+ consecutive eligible misses) |
| PURPLE | Long-term project container |
| BLUE   | Fixed-date/scheduled event |

Color is derived, never stored. See `core/state_engine.derive_color`.

## Missed-task handling & recovery

See `core/state_engine.reconcile` and
`core/scheduling_engine.rebalance_after_missed_task`. A missed task must
not simply pile onto today's load — lower-priority work is pushed later
to make realistic room.

## Rollover behavior

`core/state_engine.reconcile(last_known_date, today, db_state)` replays
each day from `last_known_date` up to (excluding) `today`, in order (not
a jump-to-today shortcut). The replay starts *at* `last_known_date`
itself, not the day after — `last_known_date` is only the last day whose
board was computed; if the app was closed before its own midnight
rollover ran, that day was never closed out, so it still needs replaying.
Each replayed day applies missed-task logic and archives/purges weekly
history when that day is a Sunday (end of its week), before computing
today's board.

`ReconciliationService.run` (wraps `reconcile`) also repairs one specific
data-integrity drift on every pass (spec §52): a task left marked
SCHEDULED with a `current_scheduled_date` but no matching `task_schedule`
row (possible if the app crashed between `ScheduleService.generate_week`
persisting the schedule and updating each task's status) is reset to
PENDING so the next Generate Week picks it back up.

## Recurrence

`core/recurrence_engine.generate_next_occurrence(rule, after_date)`
returns the next occurrence date strictly after `after_date`:

```
daily            -> after_date + interval days
weekly           -> after_date + interval * 7 days
monthly          -> same day-of-month, interval months later,
                    clamped to the target month's last day
                    (e.g. Jan 31 + 1 month -> Feb 28/29)
custom_weekdays  -> the next date (within 7 days) whose weekday
                    is in the rule's weekday set; interval is
                    not used for this frequency
```

Recurring definitions persist indefinitely; occurrences do not
(spec §44). `services/recurrence_service.ensure_next_occurrence`, called
from `TaskService.complete_task` when the completed task has a
`recurrence_rule_id`, never mutates the just-completed task — it only
ever `create()`s a brand-new Task row for the next occurrence, with
`due_date` (if any) shifted by the same delta as the rule's next-anchor
calculation. A recurring task with no due date anchors instead on its own
`completed_at`, purely to compute the next occurrence's date for the
following recurrence — there is no other field left to shift.

## Due-date normalization

`core/date_service.normalize_due_date(due_date, as_of=None)` clamps a
past due date forward to today (default `as_of`) — a due date is never
allowed to sit in the past. `services/task_service.TaskService` applies
this on every task-creation and task-update path (`create_task`,
`update_task`), not just quick-entry shorthand, so it can never be
bypassed by adding another entry point later.
