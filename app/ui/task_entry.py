"""Quick task entry (spec §25/§28) — title required, Enter to save,
everything else defaults. Call into app.services.task_service only."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class QuickTaskEntry(QWidget):
    task_created = Signal(int)

    def __init__(self, task_service, parent=None):
        super().__init__(parent)
        self._task_service = task_service

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText("What needs to happen?")
        self._input.returnPressed.connect(self._submit)
        layout.addWidget(self._input, stretch=1)

        add_button = QPushButton("Add Task")
        add_button.clicked.connect(self._submit)
        layout.addWidget(add_button)

    def focus_input(self) -> None:
        self._input.setFocus()

    def _submit(self) -> None:
        title = self._input.text().strip()
        if not title:
            return
        task = self._task_service.create_task(title)
        self._input.clear()
        self.task_created.emit(task.id)
