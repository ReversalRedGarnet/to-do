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
3. Place each task on the earliest day within
   `[available_from, due_date]` with remaining capacity under the
   utilization target.
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
