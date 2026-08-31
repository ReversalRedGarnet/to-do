"""
Application configuration and tunable constants.

These are the v1 defaults referenced in ALGORITHM.md — treat this as the
single source of truth so the scheduler, tests, and UI stay in sync.
"""

from enum import Enum


class Capacity(Enum):
    LOW = 3
    MEDIUM = 6
    HIGH = 9


# Effort scale (1-5) -> abstract capacity units consumed.
# Super-linear: larger tasks cost disproportionately more room.
EFFORT_UNITS = {
    1: 1,
    2: 2,
    3: 3,
    4: 5,
    5: 8,
}

# Default weekly capacity profile (Monday = 0 ... Sunday = 6)
DEFAULT_WEEKLY_CAPACITY = [
    Capacity.MEDIUM,  # Monday
    Capacity.MEDIUM,  # Tuesday
    Capacity.MEDIUM,  # Wednesday
    Capacity.MEDIUM,  # Thursday
    Capacity.MEDIUM,  # Friday
    Capacity.HIGH,    # Saturday
    Capacity.LOW,     # Sunday
]

# The scheduler intentionally leaves slack; it will not fill a day past
# this fraction of its capacity under normal (non-overcommitted) placement.
UTILIZATION_TARGET = 0.75

# Days used to normalize deadline pressure to a 0-5 scale.
DEADLINE_PLANNING_HORIZON_DAYS = 14

# Missed-opportunity thresholds for state_engine color transitions.
ORANGE_THRESHOLD = 1  # missed opportunities
RED_THRESHOLD = 3      # consecutive missed opportunities (eligible days only)

# Priority score component weights (must sum to 1.0).
PRIORITY_WEIGHTS = {
    "importance": 0.30,
    "urgency": 0.20,
    "seriousness": 0.25,
    "deadline_pressure": 0.15,
    "context_adjustment": 0.10,
}

DEFAULT_CATEGORIES = [
    "School",
    "Work",
    "Family",
    "Personal",
    "Hobby",
    "Health",
    "Finance",
    "Other",
]

# Sensible defaults applied during quick task entry (Sunday planning flow).
DEFAULT_TASK_VALUES = {
    "importance": 3,
    "urgency": 3,
    "seriousness": 3,
    "effort": 2,
    "category": "Personal",
}

# Path resolution — override via environment or a future settings table.
APP_NAME = "TaskPlanner"
DATABASE_FILENAME = "task_planner.db"
