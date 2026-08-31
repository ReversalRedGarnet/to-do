"""Data access for the tasks table. No business logic here — see services/."""


class TaskRepository:
    def __init__(self, conn):
        self._conn = conn

    # TODO: create, get_by_id, list_for_week, update_status, etc.
