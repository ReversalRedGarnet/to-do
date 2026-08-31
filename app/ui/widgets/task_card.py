"""Reusable task card widget — no business logic, only display + signal
emission. Callers (weekly_board, main_window) wire signals to services."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.core.state_engine import Color
from app.models.task import TaskStatus

_ACTIONABLE_STATUSES = (TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.DEFERRED)

_COLOR_HEX = {
    Color.GREEN: "#2e7d32",
    Color.YELLOW: "#f9a825",
    Color.ORANGE: "#ef6c00",
    Color.RED: "#c62828",
    Color.PURPLE: "#6a1b9a",
    Color.BLUE: "#1565c0",
    None: "#9e9e9e",
}


class TaskCard(QFrame):
    complete_clicked = Signal(int)
    defer_clicked = Signal(int)
    edit_clicked = Signal(int)

    def __init__(self, task, color, parent=None):
        super().__init__(parent)
        self.task_id = task.id
        self._build(task, color)

    def _build(self, task, color):
        hex_color = _COLOR_HEX.get(color, _COLOR_HEX[None])
        self.setObjectName("taskCard")
        self.setStyleSheet(
            f"#taskCard {{ border-left: 4px solid {hex_color}; "
            "background: palette(base); border-radius: 4px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)

        title = QLabel(task.title)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 600;")
        outer.addWidget(title)

        meta_bits = [task.category]
        if task.due_date:
            meta_bits.append(f"due {task.due_date.isoformat()}")
        meta_label = QLabel(" · ".join(meta_bits))
        meta_label.setWordWrap(True)
        outer.addWidget(meta_label)

        button_row = QHBoxLayout()
        if task.task_type.value != "fixed_event" and task.status in _ACTIONABLE_STATUSES:
            complete_btn = QPushButton("Complete")
            complete_btn.clicked.connect(lambda: self.complete_clicked.emit(task.id))
            button_row.addWidget(complete_btn)

            defer_btn = QPushButton("Defer")
            defer_btn.clicked.connect(lambda: self.defer_clicked.emit(task.id))
            button_row.addWidget(defer_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(task.id))
        button_row.addWidget(edit_btn)
        outer.addLayout(button_row)
