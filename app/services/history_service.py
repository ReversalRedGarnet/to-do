"""Owns the one-week rolling history retention policy (spec §22-23)."""


class HistoryService:
    def __init__(self, history_repository):
        self._history = history_repository

    # TODO: archive_week, purge_older_than_previous_week
