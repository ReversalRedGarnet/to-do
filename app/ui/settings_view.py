"""Settings screen (spec §27/§47), reorganized into grouped sections
(Phase 6): Notifications, Planning, Week generation, Data, Appearance.
Calls into app.services.settings_service only."""

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from app.config.settings import Capacity
from app.database.db import default_db_path
from app.ui.theme import apply_theme

_DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_CAPACITY_OPTIONS = [c.name for c in Capacity]  # LOW, MEDIUM, HIGH

_AGGRESSIVENESS_OPTIONS = [
    ("relaxed", "Relaxed — leave more slack"),
    ("standard", "Standard"),
    ("aggressive", "Aggressive — fill days more fully"),
]
_THEME_OPTIONS = [
    ("system", "Match system"),
    ("light", "Light"),
    ("dark", "Dark"),
]


class SettingsView(QWidget):
    def __init__(self, settings_service, parent=None, *, app=None):
        super().__init__(parent)
        self._settings_service = settings_service
        self._app = app

        outer = QVBoxLayout(self)

        outer.addWidget(self._build_notifications_group())
        outer.addWidget(self._build_planning_group())
        outer.addWidget(self._build_week_generation_group())
        outer.addWidget(self._build_data_group())
        outer.addWidget(self._build_appearance_group())

        self._status_label = QLabel("")
        outer.addWidget(self._status_label)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        outer.addWidget(save_button)

        outer.addStretch()

        self.refresh()

    def _build_notifications_group(self) -> QGroupBox:
        group = QGroupBox("Notifications")
        layout = QVBoxLayout(group)
        self._notifications_enabled = QCheckBox("Enable notifications")
        layout.addWidget(self._notifications_enabled)
        self._sunday_reminder_enabled = QCheckBox(
            "Remind me on Sundays if next week isn't planned"
        )
        layout.addWidget(self._sunday_reminder_enabled)
        return group

    def _build_planning_group(self) -> QGroupBox:
        group = QGroupBox("Planning")
        layout = QVBoxLayout(group)
        layout.addWidget(QLabel("Daily capacity"))
        capacity_form = QFormLayout()
        self._capacity_boxes = []
        for label in _DAY_LABELS:
            box = QComboBox()
            box.addItems(_CAPACITY_OPTIONS)
            capacity_form.addRow(label, box)
            self._capacity_boxes.append(box)
        layout.addLayout(capacity_form)
        return group

    def _build_week_generation_group(self) -> QGroupBox:
        group = QGroupBox("Week generation")
        layout = QVBoxLayout(group)

        form = QFormLayout()
        self._aggressiveness = QComboBox()
        for value, label in _AGGRESSIVENESS_OPTIONS:
            self._aggressiveness.addItem(label, value)
        form.addRow("Aggressiveness", self._aggressiveness)
        layout.addLayout(form)

        self._weekend_allowed = QCheckBox("Allow scheduling work on weekends")
        layout.addWidget(self._weekend_allowed)

        self._allow_low_priority_automove = QCheckBox(
            "Allow Generate Week to move already-placed low-priority work"
        )
        layout.addWidget(self._allow_low_priority_automove)
        return group

    def _build_data_group(self) -> QGroupBox:
        group = QGroupBox("Data")
        layout = QVBoxLayout(group)
        path_label = QLabel(f"Database file: {default_db_path()}")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        undo_note = QLabel(
            "Undo (Generate Week, Delete) is available only for the rest of the current "
            "session — it is not saved, and is lost when the app is closed."
        )
        undo_note.setWordWrap(True)
        undo_note.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(undo_note)
        return group

    def _build_appearance_group(self) -> QGroupBox:
        group = QGroupBox("Appearance")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        self._theme = QComboBox()
        for value, label in _THEME_OPTIONS:
            self._theme.addItem(label, value)
        form.addRow("Theme", self._theme)
        layout.addLayout(form)
        return group

    def refresh(self) -> None:
        self._status_label.setText("")
        settings = self._settings_service.get()
        self._notifications_enabled.setChecked(settings.notifications_enabled)
        self._sunday_reminder_enabled.setChecked(settings.sunday_reminder_enabled)
        for box, capacity_name in zip(self._capacity_boxes, settings.daily_capacities):
            index = box.findText(capacity_name)
            box.setCurrentIndex(max(index, 0))

        agg_index = self._aggressiveness.findData(settings.week_gen_aggressiveness)
        self._aggressiveness.setCurrentIndex(max(agg_index, 0))
        self._weekend_allowed.setChecked(settings.week_gen_weekend_allowed)
        self._allow_low_priority_automove.setChecked(settings.week_gen_allow_low_priority_automove)

        theme_index = self._theme.findData(settings.theme_preference)
        self._theme.setCurrentIndex(max(theme_index, 0))

    def _save(self) -> None:
        self._settings_service.update(
            notifications_enabled=self._notifications_enabled.isChecked(),
            sunday_reminder_enabled=self._sunday_reminder_enabled.isChecked(),
            daily_capacities=[box.currentText() for box in self._capacity_boxes],
            week_gen_aggressiveness=self._aggressiveness.currentData(),
            week_gen_weekend_allowed=self._weekend_allowed.isChecked(),
            week_gen_allow_low_priority_automove=self._allow_low_priority_automove.isChecked(),
            theme_preference=self._theme.currentData(),
        )
        if self._app is not None:
            apply_theme(self._app, self._theme.currentData())
        self._status_label.setText("Saved.")
