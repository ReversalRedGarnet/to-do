"""Data access for the singleton settings row. No business logic here."""

import json

from app.models.settings import AppSettings


class SettingsRepository:
    def __init__(self, conn):
        self._conn = conn

    def get(self) -> AppSettings:
        row = self._conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        return AppSettings(
            daily_capacities=json.loads(row["daily_capacities"]),
            utilization_target=row["utilization_target"],
            priority_weights=json.loads(row["priority_weights"]),
            notifications_enabled=bool(row["notifications_enabled"]),
            sunday_reminder_enabled=bool(row["sunday_reminder_enabled"]),
            week_starts_monday=bool(row["week_starts_monday"]),
        )

    def update(self, settings: AppSettings) -> None:
        self._conn.execute(
            """
            UPDATE settings SET
                daily_capacities = ?, utilization_target = ?, priority_weights = ?,
                notifications_enabled = ?, sunday_reminder_enabled = ?,
                week_starts_monday = ?
            WHERE id = 1
            """,
            (
                json.dumps(settings.daily_capacities), settings.utilization_target,
                json.dumps(settings.priority_weights),
                int(settings.notifications_enabled), int(settings.sunday_reminder_enabled),
                int(settings.week_starts_monday),
            ),
        )
        self._conn.commit()
