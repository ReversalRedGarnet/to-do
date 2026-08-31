"""Main application window: sidebar navigation + content area.
No business logic here — delegate to app.services.*"""

from datetime import date

from PySide6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from app.core.date_service import week_start
from app.core.state_engine import derive_color
from app.ui.project_view import ProjectView
from app.ui.task_editor import TaskEditorDialog
from app.ui.task_entry import QuickTaskEntry
from app.ui.weekly_board import WeeklyBoard
from app.ui.widgets.task_card import TaskCard


class TodayPanel(QWidget):
    def __init__(self, task_service, schedule_service, category_repository, parent=None):
        super().__init__(parent)
        self._task_service = task_service
        self._schedule_service = schedule_service
        self._categories = category_repository

        outer = QVBoxLayout(self)
        self._entry = QuickTaskEntry(task_service)
        self._entry.task_created.connect(lambda _id: self.refresh())
        outer.addWidget(self._entry)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        outer.addWidget(scroll)

        self.refresh()

    def refresh(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today = date.today()
        schedule = self._schedule_service.get_week(week_start(today))
        entries = schedule.get(today, [])
        categories = self._categories.list_all()

        for entry in entries:
            task = self._task_service.get_task(entry.task_id)
            if task is None:
                continue
            color = derive_color(task, today, {"expected_date": entry.scheduled_date})
            card = TaskCard(task, color)
            card.complete_clicked.connect(self._on_complete)
            card.defer_clicked.connect(self._on_defer)
            card.edit_clicked.connect(lambda tid, t=task, cats=categories: self._on_edit(t, cats))
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

    def _on_complete(self, task_id: int) -> None:
        self._task_service.complete_task(task_id)
        self.refresh()

    def _on_defer(self, task_id: int) -> None:
        from datetime import timedelta
        tomorrow = date.today() + timedelta(days=1)
        self._task_service.defer_task(task_id, tomorrow)
        self._schedule_service.move_task(task_id, week_start(date.today()), tomorrow)
        self.refresh()

    def _on_edit(self, task, categories) -> None:
        dialog = TaskEditorDialog(task, categories, self._task_service, self)
        if dialog.exec():
            self.refresh()


def build_main_window(task_service, schedule_service, project_repository, category_repository):
    """Constructs the QMainWindow. Caller (main.py) owns the QApplication
    and event loop — this only builds the widget tree."""
    window = QMainWindow()
    window.setWindowTitle("My Week")
    window.resize(1100, 700)

    central = QWidget()
    root_layout = QHBoxLayout(central)

    sidebar = QListWidget()
    sidebar.setMaximumWidth(160)
    for label in ("Today", "This Week", "Projects"):
        QListWidgetItem(label, sidebar)

    stack = QStackedWidget()

    today_panel = TodayPanel(task_service, schedule_service, category_repository)
    stack.addWidget(today_panel)

    week_panel = QWidget()
    week_layout = QVBoxLayout(week_panel)
    week_entry = QuickTaskEntry(task_service)
    week_board = WeeklyBoard(task_service, schedule_service, category_repository)
    week_entry.task_created.connect(lambda _id: week_board.refresh())

    generate_button = QPushButton("Generate Week")
    generate_button.clicked.connect(lambda: (schedule_service.generate_week(week_start(date.today())), week_board.refresh()))

    top_row = QHBoxLayout()
    top_row.addWidget(week_entry, stretch=1)
    top_row.addWidget(generate_button)
    week_layout.addLayout(top_row)
    week_layout.addWidget(week_board)
    stack.addWidget(week_panel)

    project_panel = ProjectView(project_repository, task_service)
    stack.addWidget(project_panel)

    sidebar.currentRowChanged.connect(stack.setCurrentIndex)
    sidebar.setCurrentRow(0)

    root_layout.addWidget(sidebar)
    root_layout.addWidget(stack, stretch=1)

    window.setCentralWidget(central)
    return window
