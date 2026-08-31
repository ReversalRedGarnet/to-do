"""Orchestrates core.scheduling_engine against real repositories."""


class ScheduleService:
    def __init__(self, task_repository, schedule_repository):
        self._tasks = task_repository
        self._schedules = schedule_repository

    # TODO: generate_week, get_week, regenerate_after_change
