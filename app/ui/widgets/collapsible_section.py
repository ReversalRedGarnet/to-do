"""A titled, collapsible group of widgets — used to keep the Today view's
"Completed (N)" bucket (and later the Projects view's "Archived (N)"
bucket) out of the way by default without losing access to it. No
business logic; purely a layout container."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent=None, start_collapsed: bool = False):
        super().__init__(parent)
        self._title = title

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self._toggle = QToolButton()
        self._toggle.setStyleSheet("QToolButton { border: none; font-weight: 600; }")
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(not start_collapsed)
        self._toggle.clicked.connect(self._on_toggle)
        outer.addWidget(self._toggle)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(4, 0, 0, 0)
        outer.addWidget(self._body)

        self._body.setVisible(not start_collapsed)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if not start_collapsed else Qt.ArrowType.RightArrow)
        self.set_count(0)

    def _on_toggle(self, checked: bool) -> None:
        self._body.setVisible(checked)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def set_count(self, count: int) -> None:
        self._toggle.setText(f"{self._title} ({count})")

    @property
    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def is_collapsed(self) -> bool:
        return not self._toggle.isChecked()

    def set_collapsed(self, collapsed: bool) -> None:
        self._toggle.setChecked(not collapsed)
        self._on_toggle(not collapsed)
