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
        """Replace every non-locked schedule row for this week with `entries`.
        Locked rows (spec §30 "Lock task to day") are left untouched."""
        self._conn.execute(
            "DELETE FROM task_schedule WHERE week_start = ? AND locked = 0",
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
        self._conn.execute(
            """
            UPDATE task_schedule SET scheduled_date = ?, manual_override = 1
            WHERE task_id = ? AND week_start = ?
            """,
            (new_date.isoformat(), task_id, week_start.isoformat()),
        )
        self._conn.commit()
