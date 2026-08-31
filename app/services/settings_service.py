"""Business logic for reading/editing persisted app settings (spec §27/§47).
UI widgets must call into this layer, never touch SettingsRepository directly."""

from typing import List, Optional

from app.models.settings import AppSettings


class SettingsService:
    def __init__(self, settings_repository):
        self._settings = settings_repository

    def get(self) -> AppSettings:
        return self._settings.get()

    def update(
        self,
        *,
        notifications_enabled: Optional[bool] = None,
        sunday_reminder_enabled: Optional[bool] = None,
        daily_capacities: Optional[List[str]] = None,
    ) -> AppSettings:
        """Partial update — only overwrites fields explicitly passed."""
        settings = self._settings.get()
        if notifications_enabled is not None:
            settings.notifications_enabled = notifications_enabled
        if sunday_reminder_enabled is not None:
            settings.sunday_reminder_enabled = sunday_reminder_enabled
        if daily_capacities is not None:
            settings.daily_capacities = daily_capacities
        self._settings.update(settings)
        return settings
