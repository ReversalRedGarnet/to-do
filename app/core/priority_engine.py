"""
Deterministic, transparent priority scoring. No machine learning.

Each component is implemented separately so weights can be tuned and each
piece can be unit tested in isolation (see spec §11, §12, tests/test_priority.py).
"""

from datetime import date
from typing import Optional

from app.config.settings import EFFORT_UNITS, PRIORITY_WEIGHTS, DEADLINE_PLANNING_HORIZON_DAYS


def calculate_importance_score(importance: int) -> float:
    """Importance is already on the 1-5 scale the weighted sum expects."""
    return float(importance)


def calculate_urgency_score(urgency: int) -> float:
    """Urgency is already on the 1-5 scale the weighted sum expects."""
    return float(urgency)


def calculate_seriousness_score(seriousness: int) -> float:
    """Seriousness is already on the 1-5 scale the weighted sum expects."""
    return float(seriousness)


def calculate_deadline_pressure(due_date: Optional[date], today: date,
                                 horizon_days: int = DEADLINE_PLANNING_HORIZON_DAYS) -> float:
    """
    Returns 0-5. No due date -> 0. Overdue -> 5 (max). Otherwise a smooth
    ramp based on days_remaining / horizon_days. See ALGORITHM.md.
    """
    if due_date is None:
        return 0.0

    days_remaining = (due_date - today).days
    if days_remaining <= 0:
        return 5.0

    pressure = 5.0 * (1 - days_remaining / horizon_days)
    return max(0.0, min(5.0, pressure))


def calculate_effort_factor(effort: int) -> float:
    """Effort influences scheduling feasibility (capacity cost), not raw
    priority weight — see EFFORT_UNITS. Used by the scheduling engine,
    not folded into calculate_priority_score."""
    return float(EFFORT_UNITS[effort])


def calculate_context_adjustment(task) -> float:
    """
    Small adjustment slot for category/context — must not dominate the
    score (spec §7: category is context, not an inherent importance
    ranking). v1 defines no category-based bias; this is a documented
    no-op extension point rather than an unimplemented feature.
    """
    return 0.0


def calculate_priority_score(task, today: date) -> float:
    """Combine components using PRIORITY_WEIGHTS. See spec §11."""
    importance_score = calculate_importance_score(task.importance)
    urgency_score = calculate_urgency_score(task.urgency)
    seriousness_score = calculate_seriousness_score(task.seriousness)
    deadline_pressure = calculate_deadline_pressure(task.due_date, today)
    context_adjustment = calculate_context_adjustment(task)

    return (
        importance_score * PRIORITY_WEIGHTS["importance"]
        + urgency_score * PRIORITY_WEIGHTS["urgency"]
        + seriousness_score * PRIORITY_WEIGHTS["seriousness"]
        + deadline_pressure * PRIORITY_WEIGHTS["deadline_pressure"]
        + context_adjustment * PRIORITY_WEIGHTS["context_adjustment"]
    )


def priority_label(score: float) -> str:
    """Display-only bucketing of the existing weighted score into a label
    a UI can show at a glance. Never a substitute for the score itself —
    purely a presentation-layer derivation (see ARCHITECTURE.md's scoring
    engine is the single source of truth)."""
    if score >= 4.0:
        return "Urgent"
    if score >= 3.0:
        return "High"
    if score >= 2.0:
        return "Normal"
    return "Low"
