"""Data access for the singleton app_state row. No business logic here."""

from datetime import date
from typing import Optional


class AppStateRepository:
    def __init__(self, conn):
        self._conn = conn

    def get_last_known_date(self) -> Optional[date]:
        row = self._conn.execute("SELECT last_known_date FROM app_state WHERE id = 1").fetchone()
        if row is None or row["last_known_date"] is None:
            return None
        return date.fromisoformat(row["last_known_date"])

    def set_last_known_date(self, value: date) -> None:
        """Only call this after a reconciliation pass completes successfully
        (see core/state_engine.reconcile) — never speculatively."""
        self._conn.execute(
            "UPDATE app_state SET last_known_date = ? WHERE id = 1",
            (value.isoformat(),),
        )
        self._conn.commit()

    def get_last_notified_date(self) -> Optional[date]:
        row = self._conn.execute("SELECT last_notified_date FROM app_state WHERE id = 1").fetchone()
        if row is None or row["last_notified_date"] is None:
            return None
        return date.fromisoformat(row["last_notified_date"])

    def set_last_notified_date(self, value: date) -> None:
        """Marks that the startup/rollover notification batch for `value`
        has already been sent, so the startup pass and the mid-session
        rollover timer can't double-fire the same day (spec §31)."""
        self._conn.execute(
            "UPDATE app_state SET last_notified_date = ? WHERE id = 1",
            (value.isoformat(),),
        )
        self._conn.commit()
