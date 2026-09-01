"""Full task edit dialog (spec §28). Calls into app.services.* only."""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLineEdit, QSpinBox, QTextEdit, QWidget,
)

from app.models.recurrence import RecurrenceFrequency

_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_FREQUENCY_LABELS = {
    None: "None",
    RecurrenceFrequency.DAILY: "Daily",
    RecurrenceFrequency.WEEKLY: "Weekly",
    RecurrenceFrequency.MONTHLY: "Monthly",
    RecurrenceFrequency.CUSTOM_WEEKDAYS: "Custom weekdays",
}


def _to_qdate(d):
    return QDate(d.year, d.month, d.day) if d else QDate()


def _from_qdate(qd: QDate):
    return qd.toPython() if qd.isValid() else None


class MoveToProjectDialog(QDialog):
    """Phase 7 right-click "Move to Project" — a small standalone picker,
    distinct from TaskEditorDialog's inline Project combo (used when only
    the project assignment needs to change, not a full edit)."""

    def __init__(self, task, project_repository, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Move to Project")
        form = QFormLayout(self)

        self._project = QComboBox()
        self._project.addItem("(None)", None)
        for project in project_repository.list_active():
            self._project.addItem(project.name, project.id)
        index = self._project.findData(task.project_id)
        self._project.setCurrentIndex(max(index, 0))
        form.addRow("Project", self._project)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def selected_project_id(self):
        return self._project.currentData()


class TaskEditorDialog(QDialog):
    def __init__(self, task, categories, task_service, recurrence_service=None,
                 project_repository=None, parent=None):
        super().__init__(parent)
        self._task = task
        self._task_service = task_service
        self._recurrence_service = recurrence_service
        self.setWindowTitle(f"Edit — {task.title}")

        form = QFormLayout(self)

        self._title = QLineEdit(task.title)
        form.addRow("Title", self._title)

        self._description = QTextEdit(task.description)
        self._description.setFixedHeight(60)
        form.addRow("Description", self._description)

        self._category = QComboBox()
        self._category.addItems(categories)
        if task.category in categories:
            self._category.setCurrentText(task.category)
        form.addRow("Category", self._category)

        self._importance = self._spin(1, 5, task.importance)
        form.addRow("Importance", self._importance)
        self._urgency = self._spin(1, 5, task.urgency)
        form.addRow("Urgency", self._urgency)
        self._seriousness = self._spin(1, 5, task.seriousness)
        form.addRow("Seriousness", self._seriousness)
        self._effort = self._spin(1, 5, task.effort)
        form.addRow("Effort", self._effort)

        self._available_from_enabled = QCheckBox("Set")
        self._available_from_enabled.setChecked(task.available_from is not None)
        self._available_from = QDateEdit(_to_qdate(task.available_from) or QDate.currentDate())
        self._available_from.setCalendarPopup(True)
        form.addRow("Available from", self._paired(self._available_from, self._available_from_enabled))

        self._due_date_enabled = QCheckBox("Set")
        self._due_date_enabled.setChecked(task.due_date is not None)
        self._due_date = QDateEdit(_to_qdate(task.due_date) or QDate.currentDate())
        self._due_date.setCalendarPopup(True)
        form.addRow("Due date", self._paired(self._due_date, self._due_date_enabled))

        if project_repository is not None:
            self._project_ids = [None]
            self._project = QComboBox()
            self._project.addItem("(None)", None)
            for project in project_repository.list_active():
                self._project.addItem(project.name, project.id)
                self._project_ids.append(project.id)
            if task.project_id is not None and task.project_id not in self._project_ids:
                current = project_repository.get_by_id(task.project_id)
                if current is not None:
                    self._project.addItem(current.name, current.id)
            index = self._project.findData(task.project_id)
            self._project.setCurrentIndex(max(index, 0))
            form.addRow("Project", self._project)
        else:
            self._project = None

        if recurrence_service is not None:
            existing_rule = recurrence_service.get_rule_for_task(task)

            self._frequency = QComboBox()
            for freq in _FREQUENCY_LABELS:
                self._frequency.addItem(_FREQUENCY_LABELS[freq], freq)
            form.addRow("Repeats", self._frequency)

            self._interval = self._spin(1, 30, existing_rule.interval if existing_rule else 1)
            form.addRow("Every N", self._interval)

            self._weekday_boxes = [QCheckBox(label) for label in _WEEKDAY_LABELS]
            weekday_row = QWidget()
            weekday_layout = QHBoxLayout(weekday_row)
            weekday_layout.setContentsMargins(0, 0, 0, 0)
            for box in self._weekday_boxes:
                weekday_layout.addWidget(box)
            form.addRow("On", weekday_row)

            if existing_rule is not None:
                index = self._frequency.findData(existing_rule.frequency)
                self._frequency.setCurrentIndex(max(index, 0))
                for day in existing_rule.weekdays or []:
                    self._weekday_boxes[day].setChecked(True)
            else:
                self._frequency.setCurrentIndex(0)  # "None"
        else:
            self._frequency = None

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _spin(lo, hi, value):
        box = QSpinBox()
        box.setRange(lo, hi)
        box.setValue(value)
        return box

    @staticmethod
    def _paired(date_edit, checkbox):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(date_edit, stretch=1)
        layout.addWidget(checkbox)
        return container

    def _save(self) -> None:
        fields = dict(
            title=self._title.text().strip() or self._task.title,
            description=self._description.toPlainText(),
            category=self._category.currentText(),
            importance=self._importance.value(),
            urgency=self._urgency.value(),
            seriousness=self._seriousness.value(),
            effort=self._effort.value(),
            available_from=_from_qdate(self._available_from.date()) if self._available_from_enabled.isChecked() else None,
            due_date=_from_qdate(self._due_date.date()) if self._due_date_enabled.isChecked() else None,
        )
        if self._project is not None:
            fields["project_id"] = self._project.currentData()
        self._task_service.update_task(self._task.id, **fields)

        if self._recurrence_service is not None:
            frequency = self._frequency.currentData()
            if frequency is None:
                self._recurrence_service.clear_recurrence(self._task.id)
            else:
                weekdays = [i for i, box in enumerate(self._weekday_boxes) if box.isChecked()] or None
                self._recurrence_service.set_recurrence(
                    self._task.id, frequency, interval=self._interval.value(), weekdays=weekdays,
                )

        self.accept()
