"""Data access for the projects table. No business logic here."""

from datetime import date
from typing import List, Optional

from app.models.project import Project


def _row_to_project(row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        active=bool(row["active"]),
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
    )


class ProjectRepository:
    def __init__(self, conn):
        self._conn = conn

    def create(self, project: Project) -> int:
        cursor = self._conn.execute(
            "INSERT INTO projects (name, description, active, due_date) VALUES (?, ?, ?, ?)",
            (project.name, project.description, int(project.active),
             project.due_date.isoformat() if project.due_date else None),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_by_id(self, project_id: int) -> Optional[Project]:
        row = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _row_to_project(row) if row else None

    def list_active(self) -> List[Project]:
        return self.list_by_active(True)

    def list_by_active(self, active: bool) -> List[Project]:
        rows = self._conn.execute(
            "SELECT * FROM projects WHERE active = ?", (int(active),)
        ).fetchall()
        return [_row_to_project(r) for r in rows]

    def update(self, project: Project) -> None:
        self._conn.execute(
            "UPDATE projects SET name = ?, description = ?, active = ?, due_date = ? WHERE id = ?",
            (project.name, project.description, int(project.active),
             project.due_date.isoformat() if project.due_date else None, project.id),
        )
        self._conn.commit()

    def archive(self, project_id: int) -> None:
        self._conn.execute("UPDATE projects SET active = 0 WHERE id = ?", (project_id,))
        self._conn.commit()
