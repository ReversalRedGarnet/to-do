"""Business logic for creating/editing/archiving projects. UI widgets
must call into this layer, never touch ProjectRepository directly (fixes
a pre-existing gap where ProjectView called the repository straight —
see ARCHITECTURE.md's UI -> services -> core/database layering rule)."""

from datetime import date
from typing import List, Optional

from app.models.project import Project


class ProjectService:
    def __init__(self, project_repository):
        self._projects = project_repository

    def create(self, name: str, description: str = "", due_date: Optional[date] = None) -> Project:
        project = Project(id=None, name=name, description=description, due_date=due_date)
        project.id = self._projects.create(project)
        return project

    def get(self, project_id: int) -> Optional[Project]:
        return self._projects.get_by_id(project_id)

    def list_active(self) -> List[Project]:
        return self._projects.list_by_active(True)

    def list_archived(self) -> List[Project]:
        return self._projects.list_by_active(False)

    def update(self, project_id: int, **fields) -> Project:
        project = self._projects.get_by_id(project_id)
        for key, value in fields.items():
            setattr(project, key, value)
        self._projects.update(project)
        return project

    def archive(self, project_id: int) -> None:
        self._projects.archive(project_id)
