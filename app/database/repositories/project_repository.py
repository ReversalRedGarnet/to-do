"""Data access for the projects table. No business logic here."""

from typing import List, Optional

from app.models.project import Project


def _row_to_project(row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        active=bool(row["active"]),
    )


class ProjectRepository:
    def __init__(self, conn):
        self._conn = conn

    def create(self, project: Project) -> int:
        cursor = self._conn.execute(
            "INSERT INTO projects (name, description, active) VALUES (?, ?, ?)",
            (project.name, project.description, int(project.active)),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_by_id(self, project_id: int) -> Optional[Project]:
        row = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _row_to_project(row) if row else None

    def list_active(self) -> List[Project]:
        rows = self._conn.execute("SELECT * FROM projects WHERE active = 1").fetchall()
        return [_row_to_project(r) for r in rows]

    def update(self, project: Project) -> None:
        self._conn.execute(
            "UPDATE projects SET name = ?, description = ?, active = ? WHERE id = ?",
            (project.name, project.description, int(project.active), project.id),
        )
        self._conn.commit()
