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
        week_gen_aggressiveness: Optional[str] = None,
        week_gen_weekend_allowed: Optional[bool] = None,
        week_gen_allow_low_priority_automove: Optional[bool] = None,
        theme_preference: Optional[str] = None,
    ) -> AppSettings:
        """Partial update — only overwrites fields explicitly passed."""
        settings = self._settings.get()
        if notifications_enabled is not None:
            settings.notifications_enabled = notifications_enabled
        if sunday_reminder_enabled is not None:
            settings.sunday_reminder_enabled = sunday_reminder_enabled
        if daily_capacities is not None:
            settings.daily_capacities = daily_capacities
        if week_gen_aggressiveness is not None:
            settings.week_gen_aggressiveness = week_gen_aggressiveness
        if week_gen_weekend_allowed is not None:
            settings.week_gen_weekend_allowed = week_gen_weekend_allowed
        if week_gen_allow_low_priority_automove is not None:
            settings.week_gen_allow_low_priority_automove = week_gen_allow_low_priority_automove
        if theme_preference is not None:
            settings.theme_preference = theme_preference
        self._settings.update(settings)
        return settings
