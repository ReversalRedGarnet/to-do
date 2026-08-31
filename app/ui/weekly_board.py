"""Week view — day columns, no hourly grid (spec §26-27). Calls into
app.services.* only; never touches repositories or core engines directly."""

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget,
)

from app.core.date_service import week_start
from app.core.state_engine import derive_color
from app.ui.task_editor import TaskEditorDialog
from app.ui.widgets.task_card import TaskCard

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class _DeferDialog(QDialog):
    def __init__(self, current_date: date, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Defer to…")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Move this task to:"))

        self._date_edit = QDateEdit(current_date + timedelta(days=1))
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setMinimumDate(current_date)
        layout.addWidget(self._date_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen_date(self) -> date:
        return self._date_edit.date().toPython()


class WeeklyBoard(QWidget):
    def __init__(self, task_service, schedule_service, category_repository, parent=None):
        super().__init__(parent)
        self._task_service = task_service
        self._schedule_service = schedule_service
        self._categories = category_repository
        self._week_start = week_start(date.today())

        self._columns = {}
        self._build_layout()
        self.refresh()

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        row = QWidget()
        row_layout = QHBoxLayout(row)

        for i, name in enumerate(_DAY_NAMES):
            day_date = self._week_start + timedelta(days=i)
            column = QVBoxLayout()
            header = QLabel(f"{name}\n{day_date.isoformat()}")
            header.setStyleSheet("font-weight: 600;")
            header.setAlignment(Qt.AlignCenter)
            column.addWidget(header)

            cards_container = QVBoxLayout()
            cards_container.addStretch()
            column.addLayout(cards_container)
            column.addStretch()

            column_widget = QWidget()
            column_widget.setLayout(column)
            column_widget.setMinimumWidth(220)
            row_layout.addWidget(column_widget)

            self._columns[day_date] = cards_container

        scroll.setWidget(row)
        outer.addWidget(scroll)

    def set_week(self, new_week_start: date) -> None:
        self._week_start = new_week_start
        self.refresh()

    def refresh(self) -> None:
        schedule = self._schedule_service.get_week(self._week_start)
        categories = self._categories.list_all()

        for day_date, container in self._columns.items():
            while container.count() > 1:  # keep the trailing stretch
                item = container.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            entries = schedule.get(day_date, [])
            for entry in entries:
                task = self._task_service.get_task(entry.task_id)
                if task is None:
                    continue
                context = {"expected_date": entry.scheduled_date}
                color = derive_color(task, date.today(), context)
                card = TaskCard(task, color)
                card.complete_clicked.connect(self._on_complete)
                card.defer_clicked.connect(self._on_defer)
                card.edit_clicked.connect(lambda tid, t=task, cats=categories: self._on_edit(t, cats))
                container.insertWidget(container.count() - 1, card)

    def _on_complete(self, task_id: int) -> None:
        self._task_service.complete_task(task_id)
        self.refresh()

    def _on_defer(self, task_id: int) -> None:
        dialog = _DeferDialog(date.today(), self)
        if dialog.exec() == QDialog.Accepted:
            new_date = dialog.chosen_date()
            self._task_service.defer_task(task_id, new_date)
            self._schedule_service.move_task(task_id, self._week_start, new_date)
            self.refresh()

    def _on_edit(self, task, categories) -> None:
        dialog = TaskEditorDialog(task, categories, self._task_service, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
