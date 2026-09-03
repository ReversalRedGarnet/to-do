"""Full task edit dialog (spec §28). Calls into app.services.* only."""

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLineEdit, QSpinBox, QTextEdit, QWidget,
)

from app.core import date_service
from app.core.title_parser import parse_title_hints
from app.models.recurrence import RecurrenceFrequency

_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_FREQUENCY_LABELS = {
    None: "None",
    RecurrenceFrequency.DAILY: "Daily",
    RecurrenceFrequency.WEEKLY: "Weekly",
    RecurrenceFrequency.MONTHLY: "Monthly",
    RecurrenceFrequency.CUSTOM_WEEKDAYS: "Custom weekdays",
}

# Live title auto-fill (see core/title_parser.py): debounce interval and
# the subtle marker distinguishing an inferred value from a typed one.
_TITLE_PARSE_DEBOUNCE_MS = 400
_AUTO_FILL_STYLE = "background-color: #eef3ff; border: 1px solid #a8c0f0;"


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
                 project_repository=None, parent=None, *, on_delete=None):
        super().__init__(parent)
        self._task = task
        self._task_service = task_service
        self._recurrence_service = recurrence_service
        self._on_delete = on_delete
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

        self._due_date_enabled = QCheckBox("Set")
        self._due_date_enabled.setChecked(task.due_date is not None)
        self._due_date = QDateEdit(_to_qdate(task.due_date) or QDate.currentDate())
        self._due_date.setCalendarPopup(True)
        form.addRow("Due date", self._paired(self._due_date, self._due_date_enabled))

        self._project_choices = []
        if project_repository is not None:
            self._project_ids = [None]
            self._project = QComboBox()
            self._project.addItem("(None)", None)
            for project in project_repository.list_active():
                self._project.addItem(project.name, project.id)
                self._project_ids.append(project.id)
                self._project_choices.append((project.id, project.name))
            if task.project_id is not None and task.project_id not in self._project_ids:
                current = project_repository.get_by_id(task.project_id)
                if current is not None:
                    self._project.addItem(current.name, current.id)
                    self._project_choices.append((current.id, current.name))
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

        self._init_title_auto_fill()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        if self._on_delete is not None:
            delete_button = buttons.addButton("Delete", QDialogButtonBox.ButtonRole.DestructiveRole)
            delete_button.clicked.connect(self._on_delete_clicked)
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

    # --- Live title auto-fill (see core/title_parser.py) ---

    def _init_title_auto_fill(self) -> None:
        self._applying_title_hints = False
        self._manually_edited = {
            "due_date": False, "effort": False, "urgency": False,
            "importance": False, "project": False,
        }
        self._auto_filled = {
            "due_date": False, "effort": False, "urgency": False,
            "importance": False, "project": False,
        }

        # Any change to these widgets while we are NOT the ones applying
        # a hint (see `_applying_title_hints`) is a manual edit — from
        # then on, further title changes must never overwrite that field
        # again for the rest of this dialog's life.
        self._due_date.dateChanged.connect(lambda _d: self._on_manual_field_edit("due_date", self._due_date))
        self._due_date_enabled.toggled.connect(lambda _c: self._on_manual_field_edit("due_date", self._due_date))
        self._effort.valueChanged.connect(lambda _v: self._on_manual_field_edit("effort", self._effort))
        self._urgency.valueChanged.connect(lambda _v: self._on_manual_field_edit("urgency", self._urgency))
        self._importance.valueChanged.connect(lambda _v: self._on_manual_field_edit("importance", self._importance))
        if self._project is not None:
            self._project.currentIndexChanged.connect(
                lambda _i: self._on_manual_field_edit("project", self._project)
            )

        self._title_debounce = QTimer(self)
        self._title_debounce.setSingleShot(True)
        self._title_debounce.setInterval(_TITLE_PARSE_DEBOUNCE_MS)
        self._title_debounce.timeout.connect(self._apply_title_hints)
        self._title.textChanged.connect(lambda _text: self._title_debounce.start())

    def _on_manual_field_edit(self, field: str, widget) -> None:
        if self._applying_title_hints:
            return
        self._manually_edited[field] = True
        self._set_auto_marker(field, widget, False)

    def _set_auto_marker(self, field: str, widget, applied: bool) -> None:
        self._auto_filled[field] = applied
        widget.setStyleSheet(_AUTO_FILL_STYLE if applied else "")

    def _apply_title_hints(self) -> None:
        """Fires ~400ms after the user pauses typing the title (the
        debounce timer set up in `_init_title_auto_fill`). Infers
        deadline/effort/urgency/importance/project from the title text
        alone and fills in whichever of those fields hasn't been
        manually edited yet this session — never the title itself."""
        hints = parse_title_hints(self._title.text(), date_service.today(), self._project_choices)

        self._applying_title_hints = True
        try:
            if hints.deadline is not None and not self._manually_edited["due_date"]:
                self._due_date_enabled.setChecked(True)
                self._due_date.setDate(_to_qdate(hints.deadline))
                self._set_auto_marker("due_date", self._due_date, True)

            if hints.effort is not None and not self._manually_edited["effort"]:
                self._effort.setValue(hints.effort)
                self._set_auto_marker("effort", self._effort, True)

            if hints.urgency is not None and not self._manually_edited["urgency"]:
                self._urgency.setValue(hints.urgency)
                self._set_auto_marker("urgency", self._urgency, True)

            if hints.importance is not None and not self._manually_edited["importance"]:
                self._importance.setValue(hints.importance)
                self._set_auto_marker("importance", self._importance, True)

            if (hints.project_id is not None and self._project is not None
                    and not self._manually_edited["project"]):
                index = self._project.findData(hints.project_id)
                if index >= 0:
                    self._project.setCurrentIndex(index)
                    self._set_auto_marker("project", self._project, True)
        finally:
            self._applying_title_hints = False

    def _save(self) -> None:
        fields = dict(
            title=self._title.text().strip() or self._task.title,
            description=self._description.toPlainText(),
            category=self._category.currentText(),
            importance=self._importance.value(),
            urgency=self._urgency.value(),
            seriousness=self._seriousness.value(),
            effort=self._effort.value(),
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

    def _on_delete_clicked(self) -> None:
        """Delegates to the same `_on_delete_requested` handler the
        context-menu path uses (confirmation + delete_task + Undo Delete)
        — passed in by the caller as `on_delete`, never reimplemented
        here. Closes without saving only if the delete actually went
        through (the handler returns False if the user declined the
        confirmation), so a cancelled delete leaves in-progress edits
        intact rather than silently discarding them."""
        if self._on_delete is not None and self._on_delete(self._task.id):
            self.reject()
