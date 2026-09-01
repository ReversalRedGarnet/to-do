"""Week view — day columns, no hourly grid (spec §26-27). Calls into
app.services.* only; never touches repositories or core engines directly."""

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from app.config.settings import EFFORT_UNITS, UTILIZATION_TARGET
from app.core.date_service import week_start
from app.core.priority_engine import calculate_priority_score
from app.core.state_engine import derive_color
from app.models.task import TaskStatus
from app.ui.task_editor import MoveToProjectDialog, TaskEditorDialog
from app.ui.widgets.task_card import TaskCard
from app.ui.widgets.task_selection_mixin import TaskSelectionMixin

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_UNSCHEDULED = "unscheduled"  # sentinel key in self._columns for the drop-to-clear column


class _DropColumn(QWidget):
    """A day (or "Unscheduled") column that accepts a dragged TaskCard's
    mime text (the task id) and forwards it to a callback — kept dumb on
    purpose, no business logic, matching this module's existing rule."""

    def __init__(self, on_drop, parent=None):
        super().__init__(parent)
        self._on_drop = on_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        try:
            task_id = int(event.mimeData().text())
        except ValueError:
            return
        self._on_drop(task_id)
        event.acceptProposedAction()


class GenerateWeekPreviewDialog(QDialog):
    """Shows what `ScheduleService.preview_week` computed before anything
    is persisted (spec: Generate Week must be previewable). Protected
    (locked/manual_override) tasks never appear as a "change" here — by
    construction their date never differs from what's already on the
    board — so they get a one-line summary instead of misleadingly
    looking untouched-but-listed."""

    def __init__(self, plan, task_titles: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Week — Preview")
        self.resize(420, 360)
        layout = QVBoxLayout(self)

        if plan.protected_task_ids:
            layout.addWidget(QLabel(
                f"{len(plan.protected_task_ids)} locked/manually-placed task(s) kept in place."
            ))

        if not plan.changes:
            layout.addWidget(QLabel("No changes — the current schedule already matches this plan."))
        else:
            layout.addWidget(QLabel(f"{len(plan.changes)} change(s):"))
            list_widget = QListWidget()
            for change in plan.changes:
                title = task_titles.get(change.task_id, f"Task #{change.task_id}")
                if change.from_date is None:
                    text = f"{title}: newly scheduled → {change.to_date.isoformat()}"
                elif change.to_date is None:
                    text = f"{title}: removed from the schedule (was {change.from_date.isoformat()})"
                else:
                    text = f"{title}: {change.from_date.isoformat()} → {change.to_date.isoformat()}"
                QListWidgetItem(text, list_widget)
            layout.addWidget(list_widget)

        note = QLabel("Applying enables a one-time Undo for the rest of this session only — "
                       "it will not be available after you close the app.")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


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


class WeeklyBoard(QWidget, TaskSelectionMixin):
    undo_available_changed = Signal(bool)
    delete_undo_available_changed = Signal(bool)

    def __init__(self, task_service, schedule_service, category_repository,
                 recurrence_service=None, parent=None, *, project_repository=None):
        super().__init__(parent)
        self._task_service = task_service
        self._schedule_service = schedule_service
        self._categories = category_repository
        self._recurrence_service = recurrence_service
        self._projects = project_repository
        self._week_start = week_start(date.today())
        self._init_selection()
        self._last_undo_snapshot = None
        self._last_deleted = None

        self._columns = {}
        self._load_labels = {}
        self._build_layout()
        self.refresh()

    def _build_day_column(self, day_date, header_text) -> QWidget:
        column = QVBoxLayout()
        header = QLabel(header_text)
        header.setAlignment(Qt.AlignCenter)
        is_today = day_date == date.today()
        header.setStyleSheet(
            "font-weight: 700; color: #1565c0;" if is_today else "font-weight: 600;"
        )
        column.addWidget(header)

        load_label = QLabel("")
        load_label.setAlignment(Qt.AlignCenter)
        load_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        column.addWidget(load_label)
        self._load_labels[day_date] = load_label

        cards_container = QVBoxLayout()
        cards_container.addStretch()
        column.addLayout(cards_container)
        column.addStretch()
        self._columns[day_date] = cards_container

        column_widget = _DropColumn(on_drop=lambda task_id, d=day_date: self._on_drop(task_id, d))
        column_widget.setLayout(column)
        column_widget.setMinimumWidth(220)
        if is_today:
            column_widget.setStyleSheet("background: rgba(21, 101, 192, 0.06);")
        return column_widget

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        row = QWidget()
        row_layout = QHBoxLayout(row)

        for i, name in enumerate(_DAY_NAMES):
            day_date = self._week_start + timedelta(days=i)
            row_layout.addWidget(self._build_day_column(day_date, f"{name}\n{day_date.isoformat()}"))

        unscheduled_column = QVBoxLayout()
        header = QLabel("Unscheduled\n(drop here to clear)")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-weight: 600; color: palette(mid);")
        unscheduled_column.addWidget(header)

        cards_container = QVBoxLayout()
        cards_container.addStretch()
        unscheduled_column.addLayout(cards_container)
        unscheduled_column.addStretch()
        self._columns[_UNSCHEDULED] = cards_container

        unscheduled_widget = _DropColumn(on_drop=self._on_unschedule)
        unscheduled_widget.setLayout(unscheduled_column)
        unscheduled_widget.setMinimumWidth(220)
        row_layout.addWidget(unscheduled_widget)

        scroll.setWidget(row)
        outer.addWidget(scroll)

    def set_week(self, new_week_start: date) -> None:
        self._week_start = new_week_start
        self.refresh()

    def run_generate_week(self) -> None:
        """Preview-then-apply flow for the "Generate Week" button (spec:
        Generate Week must be previewable and undoable, and must never
        silently move a locked/manually-placed task)."""
        plan = self._schedule_service.preview_week(self._week_start)
        task_titles = {}
        for change in plan.changes:
            task = self._task_service.get_task(change.task_id)
            if task is not None:
                task_titles[change.task_id] = task.title

        dialog = GenerateWeekPreviewDialog(plan, task_titles, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._last_undo_snapshot = self._schedule_service.apply_plan(plan)
            self.refresh()
            self.undo_available_changed.emit(True)

    def undo_last_generate(self) -> None:
        if self._last_undo_snapshot is None:
            return
        self._schedule_service.undo_plan(self._last_undo_snapshot)
        self._last_undo_snapshot = None
        self.refresh()
        self.undo_available_changed.emit(False)

    def refresh(self) -> None:
        schedule = self._schedule_service.get_week(self._week_start)
        categories = self._categories.list_all()
        still_present_ids = set()
        scheduled_task_ids = {
            entry.task_id for entries in schedule.values() for entry in entries
        }

        for day_date, container in self._columns.items():
            if day_date == _UNSCHEDULED:
                continue
            self._clear_container(container)

            entries = schedule.get(day_date, [])
            day_load = 0.0
            for entry in entries:
                task = self._task_service.get_task(entry.task_id)
                if task is None or task.status == TaskStatus.CANCELLED:
                    continue
                still_present_ids.add(task.id)
                day_load += EFFORT_UNITS[task.effort]
                context = {"expected_date": entry.scheduled_date}
                color = derive_color(task, date.today(), context)
                card = TaskCard(task, color)
                card.set_selected(task.id == self._selected_task_id)
                card.complete_clicked.connect(self._on_complete)
                card.defer_clicked.connect(self._on_defer)
                card.edit_clicked.connect(lambda tid, t=task, cats=categories: self._on_edit(t, cats))
                card.card_clicked.connect(self._handle_card_click)
                card.delete_requested.connect(self._on_delete_requested)
                card.duplicate_requested.connect(self._on_duplicate)
                card.move_to_project_requested.connect(self._on_move_to_project)
                container.insertWidget(container.count() - 1, card)

            self._update_load_label(day_date, day_load)

        unscheduled_container = self._columns[_UNSCHEDULED]
        self._clear_container(unscheduled_container)
        for task in self._unscheduled_candidates(scheduled_task_ids):
            still_present_ids.add(task.id)
            card = TaskCard(task, None, show_defer=False)
            card.set_selected(task.id == self._selected_task_id)
            card.complete_clicked.connect(self._on_complete)
            card.edit_clicked.connect(lambda tid, t=task, cats=categories: self._on_edit(t, cats))
            card.card_clicked.connect(self._handle_card_click)
            card.delete_requested.connect(self._on_delete_requested)
            card.duplicate_requested.connect(self._on_duplicate)
            card.move_to_project_requested.connect(self._on_move_to_project)
            unscheduled_container.insertWidget(unscheduled_container.count() - 1, card)

        if self._selected_task_id not in still_present_ids:
            self._selected_task_id = None

    @staticmethod
    def _clear_container(container) -> None:
        while container.count() > 1:  # keep the trailing stretch
            item = container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_load_label(self, day_date, used: float) -> None:
        label = self._load_labels.get(day_date)
        if label is None:
            return
        capacity = self._schedule_service.capacity_for_day(day_date)
        target = capacity.value * UTILIZATION_TARGET
        if used > capacity.value:
            style = "color: #c62828; font-size: 11px;"
        elif used > target:
            style = "color: #ef6c00; font-size: 11px;"
        else:
            style = "color: palette(mid); font-size: 11px;"
        label.setStyleSheet(style)
        label.setText(f"{used:g}/{capacity.value} load")

    def _unscheduled_candidates(self, scheduled_task_ids) -> list:
        """Bounded, priority-sorted set of tasks worth showing as drop-in
        candidates for this week — not "every undated task ever": only
        active, never-scheduled work whose due date (if any) falls within
        the displayed week, and isn't already placed somewhere this week."""
        week_end = self._week_start + timedelta(days=6)
        candidates = [
            t for t in self._task_service.list_all()
            if t.status == TaskStatus.PENDING
            and t.id not in scheduled_task_ids
            and (t.due_date is None or self._week_start <= t.due_date <= week_end)
        ]
        candidates.sort(key=lambda t: calculate_priority_score(t, date.today()), reverse=True)
        return candidates

    def _on_drop(self, task_id: int, day_date) -> None:
        task = self._task_service.get_task(task_id)
        if task is None or task.status == TaskStatus.CANCELLED:
            return
        self._schedule_service.schedule_task_to_day(task_id, self._week_start, day_date)
        self._task_service.schedule_to_day(task_id, day_date)
        self.refresh()

    def _on_unschedule(self, task_id: int) -> None:
        task = self._task_service.get_task(task_id)
        if task is None or task.status == TaskStatus.CANCELLED:
            return
        self._schedule_service.unschedule_task(task_id, self._week_start)
        self._task_service.unschedule_task(task_id)
        self.refresh()

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
        dialog = TaskEditorDialog(
            task, categories, self._task_service,
            recurrence_service=self._recurrence_service, project_repository=self._projects, parent=self,
            on_delete=self._on_delete_requested,
        )
        if dialog.exec() == QDialog.Accepted:
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
        self.delete_undo_available_changed.emit(True)
        self.refresh()
        return True

    def undo_last_delete(self) -> None:
        if self._last_deleted is None:
            return
        restored = self._task_service.restore_task(self._last_deleted)
        if restored.current_scheduled_date is not None:
            self._schedule_service.schedule_task_to_day(
                restored.id, week_start(restored.current_scheduled_date), restored.current_scheduled_date,
            )
        self._last_deleted = None
        self.delete_undo_available_changed.emit(False)
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
