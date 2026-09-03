"""Reusable task card widget — no business logic, only display + signal
emission. Callers (weekly_board, main_window) wire signals to services."""

from datetime import date

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout,
)

from app.core.priority_engine import calculate_priority_score, priority_label
from app.core.state_engine import Color
from app.models.task import TaskStatus
from app.ui.style import ACCENT_HEX, FONT_META, FONT_TITLE, RADIUS_LG, is_dark_active, make_category_dot

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

_SELECTION_OUTLINE = ACCENT_HEX

_STATUS_LABELS = {
    TaskStatus.PENDING: "Unscheduled",
    TaskStatus.SCHEDULED: "Scheduled",
    TaskStatus.COMPLETED: "Completed",
    TaskStatus.DEFERRED: "Deferred",
    TaskStatus.CANCELLED: "Cancelled",
}


class TaskCard(QFrame):
    complete_clicked = Signal(int)
    defer_clicked = Signal(int)
    edit_clicked = Signal(int)
    card_clicked = Signal(int)  # selection — distinct from the action buttons above
    delete_requested = Signal(int)
    duplicate_requested = Signal(int)
    move_to_project_requested = Signal(int)
    lock_toggle_requested = Signal(int)

    def __init__(self, task, color, parent=None, *, project_lookup=None, today=None, show_defer=True,
                 show_lock=False, locked=False):
        super().__init__(parent)
        self.task_id = task.id
        self.task_status = task.status
        self._is_fixed_event = task.task_type.value == "fixed_event"
        self._hex_color = _COLOR_HEX.get(color, _COLOR_HEX[None])
        self._selected = False
        self._show_lock = show_lock
        self._locked = locked
        self._draggable = not self._is_fixed_event and task.status in _ACTIONABLE_STATUSES and not locked
        self._press_pos = None
        self._build(task, project_lookup or {}, today, show_defer)

    def _build(self, task, project_lookup, today, show_defer) -> None:
        self.setObjectName("taskCard")
        self._apply_style()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        title = QLabel(task.title)
        title.setWordWrap(True)
        title.setStyleSheet(FONT_TITLE)
        outer.addWidget(title)

        meta_bits = [task.category]
        score = calculate_priority_score(task, today or date.today())
        meta_bits.append(priority_label(score))
        meta_bits.append(f"Effort {task.effort}")
        meta_bits.append(_STATUS_LABELS.get(task.status, task.status.value))
        if task.due_date:
            meta_bits.append(f"due {task.due_date.isoformat()}")
        project_name = project_lookup.get(task.project_id) if task.project_id else None
        if project_name:
            meta_bits.append(project_name)
        if self._show_lock and self._locked:
            meta_bits.append("🔒 Locked")

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        meta_row.addWidget(make_category_dot(task.category, is_dark_active()))
        meta_label = QLabel(" · ".join(meta_bits))
        meta_label.setWordWrap(True)
        meta_label.setStyleSheet(FONT_META)
        meta_row.addWidget(meta_label, stretch=1)
        outer.addLayout(meta_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        if task.task_type.value != "fixed_event" and task.status in _ACTIONABLE_STATUSES:
            complete_box = QCheckBox("Done")
            complete_box.setChecked(False)
            complete_box.stateChanged.connect(
                lambda state: self.complete_clicked.emit(task.id) if state else None
            )
            button_row.addWidget(complete_box)

            if show_defer:
                defer_btn = QPushButton("Defer")
                defer_btn.clicked.connect(lambda: self.defer_clicked.emit(task.id))
                button_row.addWidget(defer_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(task.id))
        button_row.addWidget(edit_btn)
        outer.addLayout(button_row)

    def _apply_style(self) -> None:
        selection_border = f"2px solid {_SELECTION_OUTLINE}" if self._selected else "2px solid transparent"
        self.setStyleSheet(
            f"#taskCard {{ border-left: 4px solid {self._hex_color}; "
            f"border-top: {selection_border}; border-right: {selection_border}; "
            f"border-bottom: {selection_border}; "
            f"background: palette(base); border-radius: {RADIUS_LG}px; }}"
        )

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.card_clicked.emit(self.task_id)
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._draggable
            and self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._press_pos = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(str(self.task_id))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_clicked.emit(self.task_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Right-click menu (spec: Complete/Reschedule/Edit/Move to
        Project/Delete/Duplicate, plus Lock/Unlock where the card
        represents a real day placement — see `show_lock`). Reschedule
        reuses the same defer_clicked signal the Defer button already
        emits — same dialog, just a second way to trigger it."""
        menu = QMenu(self)
        actionable = not self._is_fixed_event and self.task_status in _ACTIONABLE_STATUSES

        if actionable:
            menu.addAction("Complete", lambda: self.complete_clicked.emit(self.task_id))
            menu.addAction("Reschedule", lambda: self.defer_clicked.emit(self.task_id))
        menu.addAction("Edit", lambda: self.edit_clicked.emit(self.task_id))
        menu.addAction("Move to Project", lambda: self.move_to_project_requested.emit(self.task_id))
        menu.addAction("Duplicate", lambda: self.duplicate_requested.emit(self.task_id))
        if self._show_lock:
            label = "Unlock" if self._locked else "Lock to this day"
            menu.addAction(label, lambda: self.lock_toggle_requested.emit(self.task_id))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.delete_requested.emit(self.task_id))
        menu.exec(event.globalPos())
