"""Data access for the task_schedule table. No business logic here."""

from datetime import date
from typing import Dict, List

from app.models.schedule import ScheduleEntry


def _row_to_entry(row) -> ScheduleEntry:
    return ScheduleEntry(
        id=row["id"],
        task_id=row["task_id"],
        week_start=date.fromisoformat(row["week_start"]),
        scheduled_date=date.fromisoformat(row["scheduled_date"]),
        schedule_reason=row["schedule_reason"],
        manual_override=bool(row["manual_override"]),
        locked=bool(row["locked"]),
    )


class ScheduleRepository:
    def __init__(self, conn):
        self._conn = conn

    def replace_week(self, week_start: date, entries: List[ScheduleEntry]) -> None:
        """Replace every non-protected schedule row for this week with
        `entries`. Locked rows (spec §30 "Lock task to day") and
        manually-overridden rows (drag-and-drop, Defer/Move — spec §29/§30
        "never silently move a manually placed task") are left untouched;
        callers building `entries` are responsible for not including a
        placement for a protected task_id, since ON CONFLICT would
        otherwise overwrite its date/reason anyway."""
        self._conn.execute(
            "DELETE FROM task_schedule WHERE week_start = ? AND locked = 0 AND manual_override = 0",
            (week_start.isoformat(),),
        )
        for entry in entries:
            self._conn.execute(
                """
                INSERT INTO task_schedule
                    (task_id, week_start, scheduled_date, schedule_reason,
                     manual_override, locked)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, week_start) DO UPDATE SET
                    scheduled_date = excluded.scheduled_date,
                    schedule_reason = excluded.schedule_reason,
                    manual_override = excluded.manual_override
                """,
                (
                    entry.task_id, entry.week_start.isoformat(),
                    entry.scheduled_date.isoformat(), entry.schedule_reason,
                    int(entry.manual_override), int(entry.locked),
                ),
            )
        self._conn.commit()

    def get_week(self, week_start: date) -> List[ScheduleEntry]:
        rows = self._conn.execute(
            "SELECT * FROM task_schedule WHERE week_start = ?",
            (week_start.isoformat(),),
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def get_week_by_day(self, week_start: date) -> Dict[date, List[ScheduleEntry]]:
        by_day: Dict[date, List[ScheduleEntry]] = {}
        for entry in self.get_week(week_start):
            by_day.setdefault(entry.scheduled_date, []).append(entry)
        return by_day

    def week_exists(self, week_start: date) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM task_schedule WHERE week_start = ? LIMIT 1",
            (week_start.isoformat(),),
        ).fetchone()
        return row is not None

    def set_locked(self, task_id: int, week_start: date, locked: bool) -> None:
        self._conn.execute(
            "UPDATE task_schedule SET locked = ? WHERE task_id = ? AND week_start = ?",
            (int(locked), task_id, week_start.isoformat()),
        )
        self._conn.commit()

    def move_task(self, task_id: int, week_start: date, new_date: date) -> None:
        """Same locked-row protection as `upsert_task_day` — a locked row
        is a no-op here rather than silently moved."""
        self._conn.execute(
            """
            UPDATE task_schedule SET scheduled_date = ?, manual_override = 1
            WHERE task_id = ? AND week_start = ? AND locked = 0
            """,
            (new_date.isoformat(), task_id, week_start.isoformat()),
        )
        self._conn.commit()

    def upsert_task_day(self, task_id: int, week_start: date, scheduled_date: date,
                         reason: str, manual_override: bool = True) -> None:
        """Unlike `move_task` (UPDATE-only, safe only when a row already
        exists), this inserts a row if the task has never been scheduled
        this week — needed for drag-and-drop from an "Unscheduled" area
        onto a day (Phase 4) and for Generate Week's apply step (Phase 3).
        The `WHERE task_schedule.locked = 0` on the conflict branch is the
        actual enforcement of "a locked task is never reassigned" at the
        data layer — every caller (drag-and-drop, missed-task rebalance,
        Generate Week's apply step) goes through this one path, so this
        is the one place that has to hold regardless of what any of them
        individually remember to check."""
        self._conn.execute(
            """
            INSERT INTO task_schedule
                (task_id, week_start, scheduled_date, schedule_reason, manual_override, locked)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(task_id, week_start) DO UPDATE SET
                scheduled_date = excluded.scheduled_date,
                schedule_reason = excluded.schedule_reason,
                manual_override = excluded.manual_override
            WHERE task_schedule.locked = 0
            """,
            (task_id, week_start.isoformat(), scheduled_date.isoformat(), reason, int(manual_override)),
        )
        self._conn.commit()

    def delete_task_from_week(self, task_id: int, week_start: date) -> None:
        self._conn.execute(
            "DELETE FROM task_schedule WHERE task_id = ? AND week_start = ?",
            (task_id, week_start.isoformat()),
        )
        self._conn.commit()

    def delete_all_for_task(self, task_id: int) -> None:
        """Every task_schedule row for this task, across every week —
        used by TaskService.cancel_task so a cancelled task's schedule
        row(s) don't linger until incidentally swept by some future
        week's replace_week call. A hard delete_task cascades this via
        the tasks table's own FK instead; cancel keeps the task row, so
        it has to do this explicitly."""
        self._conn.execute("DELETE FROM task_schedule WHERE task_id = ?", (task_id,))
        self._conn.commit()
