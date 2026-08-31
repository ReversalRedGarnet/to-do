"""Data access for the fixed_events table. No business logic here."""

from datetime import date
from typing import List

from app.models.fixed_event import FixedEvent


def _row_to_event(row) -> FixedEvent:
    return FixedEvent(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        event_date=date.fromisoformat(row["event_date"]),
        event_time=row["event_time"],
        category=row["category"],
        capacity_cost=row["capacity_cost"],
    )


class FixedEventRepository:
    def __init__(self, conn):
        self._conn = conn

    def create(self, event: FixedEvent) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO fixed_events
                (title, description, event_date, event_time, category, capacity_cost)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.title, event.description, event.event_date.isoformat(),
                event.event_time, event.category, event.capacity_cost,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def list_between(self, start: date, end: date) -> List[FixedEvent]:
        rows = self._conn.execute(
            "SELECT * FROM fixed_events WHERE event_date BETWEEN ? AND ? ORDER BY event_date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def delete(self, event_id: int) -> None:
        self._conn.execute("DELETE FROM fixed_events WHERE id = ?", (event_id,))
        self._conn.commit()
