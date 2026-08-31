"""Full task edit dialog (spec §28). Calls into app.services.task_service only."""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QSpinBox, QTextEdit,
)


def _to_qdate(d):
    return QDate(d.year, d.month, d.day) if d else QDate()


def _from_qdate(qd: QDate):
    return qd.toPython() if qd.isValid() else None


class TaskEditorDialog(QDialog):
    def __init__(self, task, categories, task_service, parent=None):
        super().__init__(parent)
        self._task = task
        self._task_service = task_service
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
        from PySide6.QtWidgets import QHBoxLayout, QWidget
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(date_edit, stretch=1)
        layout.addWidget(checkbox)
        return container

    def _save(self) -> None:
        self._task_service.update_task(
            self._task.id,
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
        self.accept()
