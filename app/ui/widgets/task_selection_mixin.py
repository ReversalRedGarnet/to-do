"""Shared card-selection bookkeeping for TodayPanel/WeeklyBoard (spec §50
keyboard shortcuts act on "the currently selected task"). Selection is
per-panel, cleared on any refresh() where the previously selected task no
longer appears, and deliberately cleared by the main window on view
switch (Ctrl+W/T/P) rather than persisting invisibly in a hidden panel."""

from typing import Optional


class TaskSelectionMixin:
    def _init_selection(self) -> None:
        self._selected_task_id: Optional[int] = None

    def get_selected_task_id(self) -> Optional[int]:
        return self._selected_task_id

    def clear_selection(self) -> None:
        if self._selected_task_id is not None:
            self._selected_task_id = None
            self.refresh()

    def _handle_card_click(self, task_id: int) -> None:
        self._selected_task_id = task_id
        self.refresh()
