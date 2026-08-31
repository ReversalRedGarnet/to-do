"""Business logic for creating/editing/completing/deferring tasks.
UI widgets must call into this layer, never touch repositories directly."""


class TaskService:
    def __init__(self, task_repository, notification_service):
        self._tasks = task_repository
        self._notifications = notification_service

    # TODO: create_task, complete_task, defer_task, move_task, cancel_task
