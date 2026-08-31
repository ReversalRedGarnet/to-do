"""Persisted application settings row (distinct from config/settings.py defaults)."""

from dataclasses import dataclass
from typing import List


@dataclass
class AppSettings:
    daily_capacities: List[str]  # 7 Capacity enum names, Monday-first
    utilization_target: float
    priority_weights: dict
    notifications_enabled: bool
    sunday_reminder_enabled: bool
    week_starts_monday: bool = True
