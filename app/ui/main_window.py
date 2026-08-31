"""Main application window: sidebar navigation + content area.
No business logic here — delegate to app.services.*"""

from datetime import date

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from app.config.settings import ROLLOVER_CHECK_INTERVAL_SECONDS
from app.core import date_service
from app.core.date_service import week_start
from app.core.state_engine import derive_color
from app.models.task import TaskStatus
from app.ui.project_view import ProjectView
from app.ui.settings_view import SettingsView
from app.ui.task_editor import TaskEditorDialog
from app.ui.task_entry import QuickTaskEntry
from app.ui.weekly_board import WeeklyBoard
from app.ui.widgets.task_card import TaskCard
from app.ui.widgets.task_selection_mixin import TaskSelectionMixin


class TodayPanel(QWidget, TaskSelectionMixin):
    def __init__(self, task_service, schedule_service, category_repository,
                 recurrence_service=None, parent=None):
        super().__init__(parent)
        self._task_service = task_service
        self._schedule_service = schedule_service
        self._categories = category_repository
        self._recurrence_service = recurrence_service
        self._init_selection()

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

    def focus_quick_add(self) -> None:
        self._entry.focus_input()

    def refresh(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today = date.today()
        schedule = self._schedule_service.get_week(week_start(today))
        entries = schedule.get(today, [])
        categories = self._categories.list_all()

        still_present_ids = set()
        for entry in entries:
            task = self._task_service.get_task(entry.task_id)
            if task is None or task.status == TaskStatus.CANCELLED:
                continue
            still_present_ids.add(task.id)
            color = derive_color(task, today, {"expected_date": entry.scheduled_date})
            card = TaskCard(task, color)
            card.set_selected(task.id == self._selected_task_id)
            card.complete_clicked.connect(self._on_complete)
            card.defer_clicked.connect(self._on_defer)
            card.edit_clicked.connect(lambda tid, t=task, cats=categories: self._on_edit(t, cats))
            card.card_clicked.connect(self._handle_card_click)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

        if self._selected_task_id not in still_present_ids:
            self._selected_task_id = None

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
        dialog = TaskEditorDialog(
            task, categories, self._task_service,
            recurrence_service=self._recurrence_service, parent=self,
        )
        if dialog.exec():
            self.refresh()

    def edit_selected(self) -> None:
        if self._selected_task_id is None:
            return
        task = self._task_service.get_task(self._selected_task_id)
        if task is not None:
            self._on_edit(task, self._categories.list_all())

    def defer_selected(self) -> None:
        if self._selected_task_id is not None:
            self._on_defer(self._selected_task_id)

    def cancel_selected(self) -> None:
        if self._selected_task_id is None:
            return
        self._task_service.cancel_task(self._selected_task_id)
        self._selected_task_id = None
        self.refresh()

    def activate_selected(self) -> None:
        """Enter: a pending/scheduled/deferred task is completed; an
        already-completed task opens its editor instead (spec §50 "Enter
        -> complete/open task depending on context")."""
        if self._selected_task_id is None:
            return
        task = self._task_service.get_task(self._selected_task_id)
        if task is None:
            return
        if task.status == TaskStatus.COMPLETED:
            self._on_edit(task, self._categories.list_all())
        else:
            self._on_complete(task.id)


def _install_rollover_timer(
    window, reconciliation_service, notification_service, app_state_repository,
    schedule_service, today_panel, week_board, project_panel,
):
    """Spec §19: a lightweight timer catches midnight passing while the app
    stays open, instead of requiring a restart. Runs the same
    ReconciliationService pass main.py uses at startup, then fires exactly
    one notify_day_rollover — never the missed-task/weekly-plan startup
    batch, which already ran once when the process launched (see
    main.py._send_startup_notifications's docstring)."""
    state = {"last_seen_today": date_service.today()}

    def _check_rollover():
        current = date_service.today()
        if current == state["last_seen_today"]:
            return

        result = reconciliation_service.run(current)
        state["last_seen_today"] = current

        today_panel.refresh()
        week_board.refresh()
        project_panel.refresh()

        if app_state_repository.get_last_notified_date() == current:
            return
        this_week_start = week_start(current)
        todays_entries = schedule_service.get_week(this_week_start).get(current, [])
        event_count = len(schedule_service.get_fixed_events_between(current, current))
        notification_service.notify_day_rollover({
            "priority_task_count": len(todays_entries),
            "event_count": event_count,
        })
        app_state_repository.set_last_notified_date(current)

    timer = QTimer(window)
    timer.timeout.connect(_check_rollover)
    timer.start(ROLLOVER_CHECK_INTERVAL_SECONDS * 1000)
    window._rollover_timer = timer  # keep a reference alive on the window


_TEXT_INPUT_WIDGET_TYPES = (QLineEdit, QTextEdit, QSpinBox, QDateEdit, QComboBox)


def _focused_widget_is_text_input() -> bool:
    return isinstance(QApplication.focusWidget(), _TEXT_INPUT_WIDGET_TYPES)


def _install_shortcuts(window, sidebar, today_panel, week_board, week_entry) -> None:
    """Spec §50. Ctrl+E/D/Delete/Enter act on "the currently selected
    task" in whichever of Today/This Week is active (Projects has no
    selectable tasks, so they no-op there); none of them fire while a
    text field has focus (don't hijack shortcuts while typing), and none
    of them fall back to "first card" when nothing is selected — they
    simply do nothing."""

    def active_selectable_panel():
        index = sidebar.currentRow()
        if index == 0:
            return today_panel
        if index == 1:
            return week_board
        return None

    def guarded(handler):
        def wrapped():
            if _focused_widget_is_text_input():
                return
            handler()
        return wrapped

    def new_task():
        index = sidebar.currentRow()
        if index == 0:
            today_panel.focus_quick_add()
        elif index == 1:
            week_entry.focus_input()

    def edit_selected():
        panel = active_selectable_panel()
        if panel is not None:
            panel.edit_selected()

    def defer_selected():
        panel = active_selectable_panel()
        if panel is not None:
            panel.defer_selected()

    def cancel_selected():
        panel = active_selectable_panel()
        if panel is not None:
            panel.cancel_selected()

    def activate_selected():
        panel = active_selectable_panel()
        if panel is not None:
            panel.activate_selected()

    shortcuts = [
        QShortcut(QKeySequence("Ctrl+N"), window),
        QShortcut(QKeySequence("Ctrl+W"), window),
        QShortcut(QKeySequence("Ctrl+T"), window),
        QShortcut(QKeySequence("Ctrl+P"), window),
        QShortcut(QKeySequence("Ctrl+E"), window),
        QShortcut(QKeySequence(Qt.Key.Key_D), window),
        QShortcut(QKeySequence(Qt.Key.Key_Delete), window),
        QShortcut(QKeySequence(Qt.Key.Key_Return), window),
        QShortcut(QKeySequence(Qt.Key.Key_Enter), window),
    ]
    shortcuts[0].activated.connect(guarded(new_task))
    shortcuts[1].activated.connect(guarded(lambda: sidebar.setCurrentRow(1)))
    shortcuts[2].activated.connect(guarded(lambda: sidebar.setCurrentRow(0)))
    shortcuts[3].activated.connect(guarded(lambda: sidebar.setCurrentRow(2)))
    shortcuts[4].activated.connect(guarded(edit_selected))
    shortcuts[5].activated.connect(guarded(defer_selected))
    shortcuts[6].activated.connect(guarded(cancel_selected))
    shortcuts[7].activated.connect(guarded(activate_selected))
    shortcuts[8].activated.connect(guarded(activate_selected))
    window._shortcuts = shortcuts  # keep references alive on the window


def build_main_window(
    task_service, schedule_service, project_repository, category_repository,
    *, recurrence_service=None, settings_service=None, reconciliation_service=None,
    notification_service=None, app_state_repository=None,
):
    """Constructs the QMainWindow. Caller (main.py) owns the QApplication
    and event loop — this only builds the widget tree.

    All keyword-only services are optional so callers that don't need
    them (tests, throwaway driver scripts) can omit them.
    `recurrence_service` enables the "Repeats" control in the task editor.
    `settings_service` adds a Settings tab to the sidebar (spec §27/§47);
    without it, no Settings tab is shown at all rather than a
    non-functional placeholder. When `reconciliation_service`/
    `notification_service`/`app_state_repository` are all given, a QTimer
    watches for the date changing while the app stays open (spec §19) and
    re-runs reconciliation + a single notify_day_rollover in place,
    without a restart."""
    window = QMainWindow()
    window.setWindowTitle("My Week")
    window.resize(1100, 700)

    central = QWidget()
    root_layout = QHBoxLayout(central)

    sidebar_labels = ["Today", "This Week", "Projects"]
    if settings_service is not None:
        sidebar_labels.append("Settings")

    sidebar = QListWidget()
    sidebar.setMaximumWidth(160)
    for label in sidebar_labels:
        QListWidgetItem(label, sidebar)

    stack = QStackedWidget()

    today_panel = TodayPanel(task_service, schedule_service, category_repository, recurrence_service)
    stack.addWidget(today_panel)

    week_panel = QWidget()
    week_layout = QVBoxLayout(week_panel)
    week_entry = QuickTaskEntry(task_service)
    week_board = WeeklyBoard(task_service, schedule_service, category_repository, recurrence_service)
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

    if settings_service is not None:
        settings_panel = SettingsView(settings_service)
        stack.addWidget(settings_panel)

    def _on_sidebar_row_changed(index: int) -> None:
        # Selection clears on view switch rather than persisting invisibly
        # in a panel that's no longer shown (spec §50).
        today_panel.clear_selection()
        week_board.clear_selection()
        stack.setCurrentIndex(index)

    sidebar.currentRowChanged.connect(_on_sidebar_row_changed)
    sidebar.setCurrentRow(0)

    root_layout.addWidget(sidebar)
    root_layout.addWidget(stack, stretch=1)

    window.setCentralWidget(central)

    _install_shortcuts(window, sidebar, today_panel, week_board, week_entry)

    if reconciliation_service is not None and notification_service is not None and app_state_repository is not None:
        _install_rollover_timer(
            window, reconciliation_service, notification_service, app_state_repository,
            schedule_service, today_panel, week_board, project_panel,
        )
    return window
