"""Quick task entry (spec §25/§28) — title required, Enter to save,
everything else defaults. Also understands a colon-delimited shorthand,
"<category>: due <when>: <title>" (e.g. "work: due today: submit form"),
parsed by core/quick_entry_parser.py — a plain-text title is still always
accepted as a fallback. Call into app.services.task_service only."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from app.core import date_service
from app.core.quick_entry_parser import parse_quick_entry


class QuickTaskEntry(QWidget):
    task_created = Signal(int)

    def __init__(self, task_service, parent=None):
        super().__init__(parent)
        self._task_service = task_service

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText('What needs to happen? (or "category: due today: title")')
        self._input.returnPressed.connect(self._submit)
        layout.addWidget(self._input, stretch=1)

        add_button = QPushButton("Add Task")
        add_button.clicked.connect(self._submit)
        layout.addWidget(add_button)

    def focus_input(self) -> None:
        self._input.setFocus()

    def _submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        parsed = parse_quick_entry(text, date_service.today())
        if not parsed.title:
            return
        task = self._task_service.create_task(
            parsed.title, category=parsed.category, due_date=parsed.due_date,
        )
        self._input.clear()
        self.task_created.emit(task.id)
