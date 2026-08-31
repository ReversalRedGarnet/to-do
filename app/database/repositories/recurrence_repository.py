"""Data access for the recurrence_rules table. No business logic here."""

from datetime import date
from typing import Optional

from app.models.recurrence import RecurrenceFrequency, RecurrenceRule


def _row_to_rule(row) -> RecurrenceRule:
    weekdays = [int(d) for d in row["weekdays"].split(",")] if row["weekdays"] else None
    return RecurrenceRule(
        id=row["id"],
        frequency=RecurrenceFrequency(row["frequency"]),
        interval=row["interval"],
        weekdays=weekdays,
        created_at=date.fromisoformat(row["created_at"]) if row["created_at"] else None,
    )


class RecurrenceRepository:
    def __init__(self, conn):
        self._conn = conn

    def create(self, rule: RecurrenceRule) -> int:
        weekdays_str = ",".join(str(d) for d in rule.weekdays) if rule.weekdays else None
        cursor = self._conn.execute(
            "INSERT INTO recurrence_rules (frequency, interval, weekdays, created_at) VALUES (?, ?, ?, ?)",
            (rule.frequency.value, rule.interval, weekdays_str,
             (rule.created_at or date.today()).isoformat()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_by_id(self, rule_id: int) -> Optional[RecurrenceRule]:
        row = self._conn.execute(
            "SELECT * FROM recurrence_rules WHERE id = ?", (rule_id,)
        ).fetchone()
        return _row_to_rule(row) if row else None

    def delete(self, rule_id: int) -> None:
        self._conn.execute("DELETE FROM recurrence_rules WHERE id = ?", (rule_id,))
        self._conn.commit()
