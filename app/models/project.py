"""Long-term project (PURPLE) domain model."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Project:
    id: Optional[int]
    name: str
    description: str
    active: bool = True

    # Progress and "next actionable item" are computed from child tasks,
    # not stored directly — see services/task_service.py.
