"""Projects screen (spec §27): active PURPLE projects, progress, and next
actionable child. Calls into app.services.task_service only."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget


class ProjectCard(QFrame):
    def __init__(self, project, progress: int, next_item, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { border-left: 4px solid #6a1b9a; background: palette(base); "
            "border-radius: 4px; padding: 4px; }"
        )
        layout = QVBoxLayout(self)

        title = QLabel(project.name)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(progress)
        layout.addWidget(bar)

        next_label = QLabel(
            f"Next actionable item: {next_item.title}" if next_item else "No open child tasks"
        )
        layout.addWidget(next_label)


class ProjectView(QWidget):
    def __init__(self, project_repository, task_service, parent=None):
        super().__init__(parent)
        self._projects = project_repository
        self._task_service = task_service

        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignTop)
        self.refresh()

    def refresh(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        projects = self._projects.list_active()
        if not projects:
            self._layout.addWidget(QLabel("No active projects yet."))
            return

        for project in projects:
            progress = self._task_service.project_progress(project.id)
            next_item = self._task_service.next_actionable_item(project.id)
            self._layout.addWidget(ProjectCard(project, progress, next_item))
