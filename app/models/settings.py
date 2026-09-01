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
    # Week generation knobs (Phase 6) — additive scheduling behavior, never
    # the LOW/MEDIUM/HIGH capacity constants themselves.
    week_gen_aggressiveness: str = "standard"  # "relaxed" | "standard" | "aggressive"
    week_gen_weekend_allowed: bool = True
    week_gen_allow_low_priority_automove: bool = True
    theme_preference: str = "system"  # "system" | "light" | "dark"
