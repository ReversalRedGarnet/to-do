"""Projects screen (spec §27): active PURPLE projects, progress, and next
actionable child. Calls into app.services.* only — never touches
ProjectRepository directly (see ProjectService's docstring)."""

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.core.state_engine import derive_color
from app.models.task import TaskStatus
from app.ui.task_editor import TaskEditorDialog
from app.ui.widgets.collapsible_section import CollapsibleSection
from app.ui.widgets.task_card import TaskCard

_STATUS_ORDER = [TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.DEFERRED, TaskStatus.COMPLETED]
_STATUS_HEADINGS = {
    TaskStatus.PENDING: "Unscheduled",
    TaskStatus.SCHEDULED: "Scheduled",
    TaskStatus.DEFERRED: "Deferred",
    TaskStatus.COMPLETED: "Completed",
}


def _to_qdate(d):
    return QDate(d.year, d.month, d.day) if d else QDate()


def _from_qdate(qd: QDate):
    return qd.toPython() if qd.isValid() else None


class _NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        form = QFormLayout(self)

        self._name = QLineEdit()
        form.addRow("Name", self._name)

        self._description = QLineEdit()
        form.addRow("Description", self._description)

        self._due_enabled = QCheckBox("Set")
        self._due_date = QDateEdit(QDate.currentDate())
        self._due_date.setCalendarPopup(True)
        due_row = QWidget()
        due_layout = QHBoxLayout(due_row)
        due_layout.setContentsMargins(0, 0, 0, 0)
        due_layout.addWidget(self._due_date, stretch=1)
        due_layout.addWidget(self._due_enabled)
        form.addRow("Due date", due_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def name(self) -> str:
        return self._name.text().strip()

    def description(self) -> str:
        return self._description.text().strip()

    def due_date(self):
        return _from_qdate(self._due_date.date()) if self._due_enabled.isChecked() else None


class ProjectDetailDialog(QDialog):
    """Tasks grouped by status (Phase 5). Editing/completing a task here
    updates it in place via TaskService, same as the Today/Week panels."""

    def __init__(self, project, project_service, task_service, categories,
                 recurrence_service=None, parent=None):
        super().__init__(parent)
        self._project = project
        self._project_service = project_service
        self._task_service = task_service
        self._categories = categories
        self._recurrence_service = recurrence_service
        self.setWindowTitle(project.name)
        self.resize(480, 520)

        outer = QVBoxLayout(self)

        if project.due_date:
            outer.addWidget(QLabel(f"Due {project.due_date.isoformat()}"))
        if project.description:
            desc = QLabel(project.description)
            desc.setWordWrap(True)
            outer.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        if project.active:
            self._archive_button = QPushButton("Archive Project")
            self._archive_button.clicked.connect(self._on_archive)
            outer.addWidget(self._archive_button)
        else:
            note = QLabel(
                "This project is archived — its child tasks are excluded from "
                "week planning and the Today view while archived."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: palette(mid);")
            outer.addWidget(note)
            self._unarchive_button = QPushButton("Restore from Archive")
            self._unarchive_button.clicked.connect(self._on_unarchive)
            outer.addWidget(self._unarchive_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._rebuild_content()

    def _rebuild_content(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        groups = self._task_service.tasks_grouped_by_status(self._project.id)
        if not groups:
            self._content_layout.addWidget(QLabel("No tasks in this project yet."))
            return

        today = date.today()
        for status in _STATUS_ORDER:
            tasks = groups.get(status, [])
            if not tasks:
                continue
            heading = QLabel(f"{_STATUS_HEADINGS[status]} ({len(tasks)})")
            heading.setStyleSheet("font-weight: 600; margin-top: 6px;")
            self._content_layout.addWidget(heading)
            for task in tasks:
                expected = task.current_scheduled_date or task.due_date
                color = derive_color(task, today, {"expected_date": expected})
                card = TaskCard(task, color, today=today, show_defer=False)
                card.complete_clicked.connect(self._on_complete)
                card.edit_clicked.connect(lambda tid, t=task: self._on_edit(t))
                self._content_layout.addWidget(card)

        self._content_layout.addStretch()

    def _on_complete(self, task_id: int) -> None:
        self._task_service.complete_task(task_id)
        self._rebuild_content()

    def _on_edit(self, task) -> None:
        dialog = TaskEditorDialog(
            task, self._categories, self._task_service,
            recurrence_service=self._recurrence_service, parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._rebuild_content()

    def _on_archive(self) -> None:
        confirm = QMessageBox.question(
            self, "Archive Project",
            f'Archive "{self._project.name}"? It will move out of the active projects list.',
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._project_service.archive(self._project.id)
            self.accept()

    def _on_unarchive(self) -> None:
        self._project_service.update(self._project.id, active=True)
        self.accept()


class ProjectCard(QFrame):
    def __init__(self, project, progress: int, open_count: int, next_item, on_open=None, parent=None):
        super().__init__(parent)
        self.setObjectName("projectCard")
        self.setStyleSheet(
            "#projectCard { border-left: 4px solid #6a1b9a; background: palette(base); "
            "border-radius: 4px; padding: 4px; }"
        )
        self.project_id = project.id
        self._on_open = on_open
        layout = QVBoxLayout(self)

        title = QLabel(project.name)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(progress)
        layout.addWidget(bar)

        meta_bits = [f"{open_count} open task(s)"]
        if project.due_date:
            meta_bits.append(f"due {project.due_date.isoformat()}")
        meta_label = QLabel(" · ".join(meta_bits))
        meta_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(meta_label)

        next_label = QLabel(
            f"Next actionable item: {next_item.title}" if next_item else "No open child tasks"
        )
        layout.addWidget(next_label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._on_open is not None:
            self._on_open()
        super().mousePressEvent(event)


class ProjectView(QWidget):
    def __init__(self, project_service, task_service, category_repository=None,
                 recurrence_service=None, parent=None):
        super().__init__(parent)
        self._projects = project_service
        self._task_service = task_service
        self._categories = category_repository
        self._recurrence_service = recurrence_service

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignTop)

        new_project_button = QPushButton("New Project")
        new_project_button.clicked.connect(self._on_new_project)
        outer.addWidget(new_project_button, alignment=Qt.AlignLeft)

        self._active_layout = QVBoxLayout()
        outer.addLayout(self._active_layout)

        self._archived_section = CollapsibleSection("Archived", start_collapsed=True)
        outer.addWidget(self._archived_section)

        outer.addStretch()
        self.refresh()

    def refresh(self) -> None:
        while self._active_layout.count():
            item = self._active_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active_projects = self._projects.list_active()
        if not active_projects:
            self._active_layout.addWidget(QLabel("No active projects yet."))
        for project in active_projects:
            progress = self._task_service.project_progress(project.id)
            open_count = self._task_service.count_open_tasks(project.id)
            next_item = self._task_service.next_actionable_item(project.id)
            card = ProjectCard(project, progress, open_count, next_item,
                                on_open=lambda p=project: self._open_detail(p))
            self._active_layout.addWidget(card)

        self._archived_section.clear_body()
        archived_projects = self._projects.list_archived()
        for project in archived_projects:
            progress = self._task_service.project_progress(project.id)
            open_count = self._task_service.count_open_tasks(project.id)
            next_item = self._task_service.next_actionable_item(project.id)
            card = ProjectCard(project, progress, open_count, next_item,
                                on_open=lambda p=project: self._open_detail(p))
            self._archived_section.body_layout.addWidget(card)
        self._archived_section.set_count(len(archived_projects))

    def _open_detail(self, project) -> None:
        dialog = ProjectDetailDialog(
            project, self._projects, self._task_service, self._categories.list_all() if self._categories else [],
            recurrence_service=self._recurrence_service, parent=self,
        )
        dialog.exec()
        self.refresh()

    def _on_new_project(self) -> None:
        dialog = _NewProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.name()
            if not name:
                return
            self._projects.create(name, dialog.description(), dialog.due_date())
            self.refresh()
