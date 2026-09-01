"""Data access for the tasks table. No business logic here — see services/."""

from datetime import date
from typing import List, Optional

from app.models.task import Task, TaskStatus, TaskType


def _escape_like(text: str) -> str:
    """Escapes SQLite LIKE wildcards so a literal search for e.g. "50%"
    doesn't get treated as a pattern."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_task(row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        task_type=TaskType(row["task_type"]),
        project_id=row["project_id"],
        category=row["category"],
        importance=row["importance"],
        urgency=row["urgency"],
        seriousness=row["seriousness"],
        effort=row["effort"],
        available_from=date.fromisoformat(row["available_from"]) if row["available_from"] else None,
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        status=TaskStatus(row["status"]),
        progress=row["progress"],
        created_at=date.fromisoformat(row["created_at"]) if row["created_at"] else None,
        completed_at=date.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        deferred_at=date.fromisoformat(row["deferred_at"]) if row["deferred_at"] else None,
        last_scheduled_date=date.fromisoformat(row["last_scheduled_date"]) if row["last_scheduled_date"] else None,
        current_scheduled_date=date.fromisoformat(row["current_scheduled_date"]) if row["current_scheduled_date"] else None,
        days_exposed=row["days_exposed"],
        times_deferred=row["times_deferred"],
        times_ignored=row["times_ignored"],
        recurrence_rule_id=row["recurrence_rule_id"],
        created_week=row["created_week"],
    )


class TaskRepository:
    def __init__(self, conn):
        self._conn = conn

    def create(self, task: Task) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO tasks
                (project_id, title, description, task_type, category,
                 importance, urgency, seriousness, effort,
                 available_from, due_date, status, progress,
                 created_at, completed_at, deferred_at,
                 last_scheduled_date, current_scheduled_date,
                 days_exposed, times_deferred, times_ignored,
                 recurrence_rule_id, created_week)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.project_id, task.title, task.description, task.task_type.value,
                task.category, task.importance, task.urgency, task.seriousness,
                task.effort,
                task.available_from.isoformat() if task.available_from else None,
                task.due_date.isoformat() if task.due_date else None,
                task.status.value, task.progress,
                task.created_at.isoformat() if task.created_at else None,
                task.completed_at.isoformat() if task.completed_at else None,
                task.deferred_at.isoformat() if task.deferred_at else None,
                task.last_scheduled_date.isoformat() if task.last_scheduled_date else None,
                task.current_scheduled_date.isoformat() if task.current_scheduled_date else None,
                task.days_exposed, task.times_deferred, task.times_ignored,
                task.recurrence_rule_id, task.created_week,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_by_id(self, task_id: int) -> Optional[Task]:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_task(row) if row else None

    def list_all(self, include_cancelled: bool = False,
                 exclude_archived_project_children: bool = False) -> List[Task]:
        query = "SELECT tasks.* FROM tasks"
        conditions = []
        if exclude_archived_project_children:
            query += " LEFT JOIN projects ON tasks.project_id = projects.id"
            conditions.append("(tasks.project_id IS NULL OR projects.active = 1)")
        if not include_cancelled:
            conditions.append("tasks.status != 'cancelled'")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        rows = self._conn.execute(query).fetchall()
        return [_row_to_task(r) for r in rows]

    def list_by_project(self, project_id: int) -> List[Task]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status != 'cancelled'",
            (project_id,),
        ).fetchall()
        return [_row_to_task(r) for r in rows]

    def list_by_ids(self, task_ids: List[int]) -> List[Task]:
        if not task_ids:
            return []
        placeholders = ",".join("?" for _ in task_ids)
        rows = self._conn.execute(
            f"SELECT * FROM tasks WHERE id IN ({placeholders})", task_ids
        ).fetchall()
        return [_row_to_task(r) for r in rows]

    def search_by_title(self, query: str) -> List[Task]:
        """Case-insensitive substring search over title (Phase 7 Ctrl+F).
        Excludes cancelled tasks, same as `list_all`'s default."""
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status != 'cancelled' AND title LIKE ? ESCAPE '\\' ORDER BY title",
            (f"%{_escape_like(query)}%",),
        ).fetchall()
        return [_row_to_task(r) for r in rows]

    def list_eligible_for_week(self, week_start: date, week_end: date) -> List[Task]:
        """Pending/scheduled tasks whose [available_from, due_date] window
        could overlap this week — candidates for generate_weekly_schedule.
        A child of an archived project is never a candidate — archiving a
        project takes its children out of week planning entirely, without
        deleting or force-completing them (they're still visible/editable
        via the project's own detail view)."""
        rows = self._conn.execute(
            """
            SELECT tasks.* FROM tasks
            LEFT JOIN projects ON tasks.project_id = projects.id
            WHERE tasks.status IN ('pending', 'scheduled')
              AND (tasks.due_date IS NULL OR tasks.due_date >= ?)
              AND (tasks.available_from IS NULL OR tasks.available_from <= ?)
              AND (tasks.project_id IS NULL OR projects.active = 1)
            """,
            (week_start.isoformat(), week_end.isoformat()),
        ).fetchall()
        return [_row_to_task(r) for r in rows]

    def update(self, task: Task) -> None:
        self._conn.execute(
            """
            UPDATE tasks SET
                project_id = ?, title = ?, description = ?, task_type = ?,
                category = ?, importance = ?, urgency = ?, seriousness = ?,
                effort = ?, available_from = ?, due_date = ?, status = ?,
                progress = ?, completed_at = ?, deferred_at = ?,
                last_scheduled_date = ?, current_scheduled_date = ?,
                days_exposed = ?, times_deferred = ?, times_ignored = ?,
                recurrence_rule_id = ?, created_week = ?
            WHERE id = ?
            """,
            (
                task.project_id, task.title, task.description, task.task_type.value,
                task.category, task.importance, task.urgency, task.seriousness,
                task.effort,
                task.available_from.isoformat() if task.available_from else None,
                task.due_date.isoformat() if task.due_date else None,
                task.status.value, task.progress,
                task.completed_at.isoformat() if task.completed_at else None,
                task.deferred_at.isoformat() if task.deferred_at else None,
                task.last_scheduled_date.isoformat() if task.last_scheduled_date else None,
                task.current_scheduled_date.isoformat() if task.current_scheduled_date else None,
                task.days_exposed, task.times_deferred, task.times_ignored,
                task.recurrence_rule_id, task.created_week,
                task.id,
            ),
        )
        self._conn.commit()

    def delete(self, task_id: int) -> None:
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()
