"""
Deterministic, transparent priority scoring. No machine learning.

Each component is implemented separately so weights can be tuned and each
piece can be unit tested in isolation (see spec §11, §12, tests/test_priority.py).
"""

from datetime import date
from typing import Optional

from app.config.settings import PRIORITY_WEIGHTS, DEADLINE_PLANNING_HORIZON_DAYS


def calculate_importance_score(importance: int) -> float:
    raise NotImplementedError


def calculate_urgency_score(urgency: int) -> float:
    raise NotImplementedError


def calculate_seriousness_score(seriousness: int) -> float:
    raise NotImplementedError


def calculate_deadline_pressure(due_date: Optional[date], today: date,
                                 horizon_days: int = DEADLINE_PLANNING_HORIZON_DAYS) -> float:
    """
    Returns 0-5. No due date -> 0. Overdue -> 5 (max). Otherwise a smooth
    ramp based on days_remaining / horizon_days. See ALGORITHM.md.
    """
    raise NotImplementedError


def calculate_effort_factor(effort: int) -> float:
    """Effort influences scheduling feasibility, not raw priority weight."""
    raise NotImplementedError


def calculate_context_adjustment(task) -> float:
    """Small adjustment slot for category/context — must not dominate the score."""
    raise NotImplementedError


def calculate_priority_score(task, today: date) -> float:
    """Combine components using PRIORITY_WEIGHTS. See spec §11."""
    raise NotImplementedError
