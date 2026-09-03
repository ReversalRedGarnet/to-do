"""Main application window: sidebar navigation + content area.
No business logic here — delegate to app.services.*"""

from datetime import date

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from app.config.settings import EFFORT_UNITS, ROLLOVER_CHECK_INTERVAL_SECONDS
from app.core import date_service
from app.core.board_view import build_today_sections
from app.core.date_service import week_start
from app.core.state_engine import derive_color
from app.models.task import TaskStatus
from app.services.project_service import ProjectService
from app.ui.project_view import ProjectView
from app.ui.search_dialog import SearchDialog
from app.ui.settings_view import SettingsView
from app.ui.task_editor import MoveToProjectDialog, TaskEditorDialog
from app.ui.task_entry import QuickTaskEntry
from app.ui.weekly_board import WeeklyBoard
from app.ui.widgets.collapsible_section import CollapsibleSection
from app.ui.widgets.task_card import TaskCard
from app.ui.widgets.task_selection_mixin import TaskSelectionMixin


class TodayPanel(QWidget, TaskSelectionMixin):
    def __init__(self, task_service, schedule_service, category_repository,
                 recurrence_service=None, parent=None, *, project_repository=None):
        super().__init__(parent)
        self._task_service = task_service
        self._schedule_service = schedule_service
        self._categories = category_repository
        self._recurrence_service = recurrence_service
        self._projects = project_repository
        self._init_selection()
        self._last_deleted = None

        outer = QVBoxLayout(self)

        header_row = QHBoxLayout()
        self._header = QLabel("")
        self._header.setStyleSheet("font-weight: 600; color: palette(mid);")
        header_row.addWidget(self._header, stretch=1)
        self._undo_delete_button = QPushButton("Undo Delete")
        self._undo_delete_button.setVisible(False)
        self._undo_delete_button.setToolTip(
            "Available only until you close the app or take another action — not saved across restarts."
        )
        self._undo_delete_button.clicked.connect(self._undo_delete)
        header_row.addWidget(self._undo_delete_button)
        outer.addLayout(header_row)

        self._entry = QuickTaskEntry(task_service)
        self._entry.task_created.connect(lambda _id: self.refresh())
        outer.addWidget(self._entry)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        sections_widget = QWidget()
        sections_layout = QVBoxLayout(sections_widget)

        self._overdue_section = CollapsibleSection("Overdue")
        self._today_section = CollapsibleSection("Today")
        self._unscheduled_section = CollapsibleSection("Unscheduled / Later")
        self._completed_section = CollapsibleSection("Completed", start_collapsed=True)
        for section in (self._overdue_section, self._today_section,
                        self._unscheduled_section, self._completed_section):
            sections_layout.addWidget(section)
        sections_layout.addStretch()

        scroll.setWidget(sections_widget)
        outer.addWidget(scroll)

        self.refresh()

    def focus_quick_add(self) -> None:
        self._entry.focus_input()

    def _render_section(self, section: CollapsibleSection, tasks, today,
                         expected_date_by_task: dict, categories, *, show_defer: bool) -> None:
        section.clear_body()
        for task in tasks:
            expected = expected_date_by_task.get(task.id, task.current_scheduled_date or task.due_date)
            color = derive_color(task, today, {"expected_date": expected})
            card = TaskCard(task, color, today=today, show_defer=show_defer)
            card.set_selected(task.id == self._selected_task_id)
            card.complete_clicked.connect(self._on_complete)
            card.defer_clicked.connect(self._on_defer)
            card.edit_clicked.connect(lambda tid, t=task, cats=categories: self._on_edit(t, cats))
            card.card_clicked.connect(self._handle_card_click)
            card.delete_requested.connect(self._on_delete_requested)
            card.duplicate_requested.connect(self._on_duplicate)
            card.move_to_project_requested.connect(self._on_move_to_project)
            section.body_layout.addWidget(card)
        section.set_count(len(tasks))

    def _update_header(self, today, sections) -> None:
        planned_units = sum(EFFORT_UNITS[t.effort] for t in sections.today)
        capacity = self._schedule_service.capacity_for_day(today)
        task_count = len(sections.overdue) + len(sections.today)
        self._header.setText(
            f"{today.strftime('%A, %B %d')}  ·  {task_count} task(s) today  ·  "
            f"planned load {planned_units:g}/{capacity.value}"
        )

    def refresh(self) -> None:
        today = date.today()
        schedule = self._schedule_service.get_week(week_start(today))
        todays_entries = schedule.get(today, [])
        scheduled_ids = {e.task_id for e in todays_entries}
        expected_date_by_task = {e.task_id: e.scheduled_date for e in todays_entries}
        categories = self._categories.list_all()

        all_tasks = self._task_service.list_all(exclude_archived_project_children=True)
        sections = build_today_sections(all_tasks, today, scheduled_ids)

        self._render_section(self._overdue_section, sections.overdue, today,
                              expected_date_by_task, categories, show_defer=False)
        self._render_section(self._today_section, sections.today, today,
                              expected_date_by_task, categories, show_defer=True)
        self._render_section(self._unscheduled_section, sections.unscheduled, today,
                              expected_date_by_task, categories, show_defer=False)
        self._render_section(self._completed_section, sections.completed, today,
                              expected_date_by_task, categories, show_defer=False)

        self._update_header(today, sections)

        still_present_ids = {
            t.id for t in sections.overdue + sections.today + sections.unscheduled + sections.completed
        }
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
            recurrence_service=self._recurrence_service, project_repository=self._projects, parent=self,
            on_delete=self._on_delete_requested,
        )
        if dialog.exec():
            self.refresh()

    def _on_delete_requested(self, task_id: int) -> bool:
        """Returns whether the task was actually deleted — lets the task
        editor's own Delete button (see task_editor.py) know whether to
        close itself, without this method needing to know it might be
        called from there as well as from a card's context menu."""
        task = self._task_service.get_task(task_id)
        if task is None:
            return False
        confirm = QMessageBox.question(
            self, "Delete Task",
            f'Delete "{task.title}"? Use Undo Delete right after if this was a mistake — '
            "it only works for the rest of this session.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return False
        self._last_deleted = self._task_service.delete_task(task_id)
        if self._selected_task_id == task_id:
            self._selected_task_id = None
        self._undo_delete_button.setVisible(True)
        self.refresh()
        return True

    def _undo_delete(self) -> None:
        if self._last_deleted is None:
            return
        restored = self._task_service.restore_task(self._last_deleted)
        if restored.current_scheduled_date is not None:
            self._schedule_service.schedule_task_to_day(
                restored.id, week_start(restored.current_scheduled_date), restored.current_scheduled_date,
            )
        self._last_deleted = None
        self._undo_delete_button.setVisible(False)
        self.refresh()

    def _on_duplicate(self, task_id: int) -> None:
        task = self._task_service.get_task(task_id)
        if task is None:
            return
        self._task_service.create_task(
            f"{task.title} (copy)", description=task.description, task_type=task.task_type,
            project_id=task.project_id, category=task.category, importance=task.importance,
            urgency=task.urgency, seriousness=task.seriousness, effort=task.effort,
            due_date=task.due_date,
        )
        self.refresh()

    def _on_move_to_project(self, task_id: int) -> None:
        if self._projects is None:
            return
        task = self._task_service.get_task(task_id)
        if task is None:
            return
        dialog = MoveToProjectDialog(task, self._projects, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._task_service.update_task(task_id, project_id=dialog.selected_project_id())
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


def _install_shortcuts(window, sidebar, today_panel, week_board, week_entry, open_search) -> None:
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
        QShortcut(QKeySequence("Ctrl+F"), window),
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
    shortcuts[9].activated.connect(open_search)  # not guarded — Ctrl+F is a chord, not plain text input
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

    today_panel = TodayPanel(task_service, schedule_service, category_repository, recurrence_service,
                              project_repository=project_repository)
    stack.addWidget(today_panel)

    week_panel = QWidget()
    week_layout = QVBoxLayout(week_panel)
    week_entry = QuickTaskEntry(task_service)
    week_board = WeeklyBoard(task_service, schedule_service, category_repository, recurrence_service,
                              project_repository=project_repository)
    week_entry.task_created.connect(lambda _id: week_board.refresh())

    generate_button = QPushButton("Generate Week")
    generate_button.clicked.connect(week_board.run_generate_week)

    undo_button = QPushButton("Undo")
    undo_button.setEnabled(False)
    undo_button.setToolTip(
        "Available only until you close the app or take another action — not saved across restarts."
    )
    undo_button.clicked.connect(week_board.undo_last_generate)
    week_board.undo_available_changed.connect(undo_button.setEnabled)

    undo_delete_button = QPushButton("Undo Delete")
    undo_delete_button.setEnabled(False)
    undo_delete_button.setToolTip(
        "Available only until you close the app or take another action — not saved across restarts."
    )
    undo_delete_button.clicked.connect(week_board.undo_last_delete)
    week_board.delete_undo_available_changed.connect(undo_delete_button.setEnabled)

    search_button = QPushButton("Search")

    top_row = QHBoxLayout()
    top_row.addWidget(week_entry, stretch=1)
    top_row.addWidget(generate_button)
    top_row.addWidget(undo_button)
    top_row.addWidget(undo_delete_button)
    top_row.addWidget(search_button)
    week_layout.addLayout(top_row)
    week_layout.addWidget(week_board)
    stack.addWidget(week_panel)

    project_service = ProjectService(project_repository)
    project_panel = ProjectView(project_service, task_service, category_repository, recurrence_service)
    stack.addWidget(project_panel)

    if settings_service is not None:
        settings_panel = SettingsView(settings_service, app=QApplication.instance())
        stack.addWidget(settings_panel)

    def _on_sidebar_row_changed(index: int) -> None:
        # Selection clears on view switch rather than persisting invisibly
        # in a panel that's no longer shown (spec §50).
        today_panel.clear_selection()
        week_board.clear_selection()
        stack.setCurrentIndex(index)
        # Each panel only refreshes itself when its own quick-add/edit/
        # delete actions fire — a task added from the Week tab's entry
        # box, for instance, never touches today_panel. Refresh every
        # data-bound panel on every switch so none can show stale state
        # just because the change that produced it happened elsewhere.
        today_panel.refresh()
        week_board.refresh()
        project_panel.refresh()
        if index == 1:
            week_board.scroll_to_first_active_day()

    sidebar.currentRowChanged.connect(_on_sidebar_row_changed)
    sidebar.setCurrentRow(0)

    root_layout.addWidget(sidebar)
    root_layout.addWidget(stack, stretch=1)

    window.setCentralWidget(central)

    def open_search() -> None:
        dialog = SearchDialog(
            task_service, category_repository, recurrence_service=recurrence_service,
            project_repository=project_repository, parent=window,
        )
        dialog.exec()
        today_panel.refresh()
        week_board.refresh()

    search_button.clicked.connect(open_search)

    _install_shortcuts(window, sidebar, today_panel, week_board, week_entry, open_search)

    if reconciliation_service is not None and notification_service is not None and app_state_repository is not None:
        _install_rollover_timer(
            window, reconciliation_service, notification_service, app_state_repository,
            schedule_service, today_panel, week_board, project_panel,
        )
    return window
