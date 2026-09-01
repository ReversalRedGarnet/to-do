"""Ctrl+F search across tasks (spec, Phase 7). Calls into
app.services.task_service only."""

from PySide6.QtWidgets import (
    QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)

from app.ui.task_editor import TaskEditorDialog


class SearchDialog(QDialog):
    def __init__(self, task_service, category_repository, recurrence_service=None,
                 project_repository=None, parent=None):
        super().__init__(parent)
        self._task_service = task_service
        self._categories = category_repository
        self._recurrence_service = recurrence_service
        self._projects = project_repository
        self.setWindowTitle("Search Tasks")
        self.resize(420, 400)

        layout = QVBoxLayout(self)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Search by title…")
        self._input.textChanged.connect(self._on_query_changed)
        layout.addWidget(self._input)

        self._results = QListWidget()
        self._results.itemDoubleClicked.connect(self._on_result_activated)
        layout.addWidget(self._results)

        self._input.setFocus()

    def _on_query_changed(self, text: str) -> None:
        self._results.clear()
        for task in self._task_service.search_tasks(text):
            item = QListWidgetItem(f"{task.title}  ·  {task.category}  ·  {task.status.value}")
            item.setData(1000, task.id)
            self._results.addItem(item)

    def _on_result_activated(self, item: QListWidgetItem) -> None:
        task_id = item.data(1000)
        task = self._task_service.get_task(task_id)
        if task is None:
            return
        dialog = TaskEditorDialog(
            task, self._categories.list_all(), self._task_service,
            recurrence_service=self._recurrence_service, project_repository=self._projects, parent=self,
        )
        dialog.exec()
