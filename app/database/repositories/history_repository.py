"""Data access for the weekly_history table. No business logic here — see
services/history_service.py for the one-week rolling retention policy."""

import json
from datetime import date
from typing import List

from app.models.history import WeeklyHistoryEntry


class HistoryRepository:
    def __init__(self, conn):
        self._conn = conn

    def archive(self, week_start: date, week_end: date, snapshot: dict) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO weekly_history (week_start, week_end, snapshot_json)
            VALUES (?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
                week_end = excluded.week_end, snapshot_json = excluded.snapshot_json
            """,
            (week_start.isoformat(), week_end.isoformat(), json.dumps(snapshot)),
        )
        self._conn.commit()
        return cursor.lastrowid

    def list_all(self) -> List[WeeklyHistoryEntry]:
        rows = self._conn.execute("SELECT * FROM weekly_history ORDER BY week_start").fetchall()
        return [
            WeeklyHistoryEntry(
                id=r["id"],
                week_start=date.fromisoformat(r["week_start"]),
                week_end=date.fromisoformat(r["week_end"]),
            )
            for r in rows
        ]

    def get_snapshot(self, week_start: date) -> dict:
        row = self._conn.execute(
            "SELECT snapshot_json FROM weekly_history WHERE week_start = ?",
            (week_start.isoformat(),),
        ).fetchone()
        return json.loads(row["snapshot_json"]) if row else {}

    def purge_older_than(self, cutoff_week_start: date) -> None:
        self._conn.execute(
            "DELETE FROM weekly_history WHERE week_start < ?",
            (cutoff_week_start.isoformat(),),
        )
        self._conn.commit()
