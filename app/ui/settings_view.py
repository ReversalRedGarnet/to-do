"""Settings screen (spec §27/§47): notifications, Sunday reminder, and
daily capacity are user-editable rather than requiring a hand-edit of the
DB. Calls into app.services.settings_service only."""

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.config.settings import Capacity

_DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_CAPACITY_OPTIONS = [c.name for c in Capacity]  # LOW, MEDIUM, HIGH


class SettingsView(QWidget):
    def __init__(self, settings_service, parent=None):
        super().__init__(parent)
        self._settings_service = settings_service

        outer = QVBoxLayout(self)

        self._notifications_enabled = QCheckBox("Enable notifications")
        outer.addWidget(self._notifications_enabled)

        self._sunday_reminder_enabled = QCheckBox(
            "Remind me on Sundays if next week isn't planned"
        )
        outer.addWidget(self._sunday_reminder_enabled)

        outer.addWidget(QLabel("Daily capacity"))
        capacity_form = QFormLayout()
        self._capacity_boxes = []
        for label in _DAY_LABELS:
            box = QComboBox()
            box.addItems(_CAPACITY_OPTIONS)
            capacity_form.addRow(label, box)
            self._capacity_boxes.append(box)
        outer.addLayout(capacity_form)

        self._status_label = QLabel("")
        outer.addWidget(self._status_label)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        outer.addWidget(save_button)

        outer.addStretch()

        self.refresh()

    def refresh(self) -> None:
        self._status_label.setText("")
        settings = self._settings_service.get()
        self._notifications_enabled.setChecked(settings.notifications_enabled)
        self._sunday_reminder_enabled.setChecked(settings.sunday_reminder_enabled)
        for box, capacity_name in zip(self._capacity_boxes, settings.daily_capacities):
            index = box.findText(capacity_name)
            box.setCurrentIndex(max(index, 0))

    def _save(self) -> None:
        self._settings_service.update(
            notifications_enabled=self._notifications_enabled.isChecked(),
            sunday_reminder_enabled=self._sunday_reminder_enabled.isChecked(),
            daily_capacities=[box.currentText() for box in self._capacity_boxes],
        )
        self._status_label.setText("Saved.")
