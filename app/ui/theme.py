"""System-aware light/dark appearance (spec §49) — "if practical," not a
blocking requirement. Detects the OS color scheme and, only when it's
dark, switches to the Fusion style with an explicit dark QPalette (the
native Windows style doesn't reliably repaint itself from QPalette
changes alone). The six state colors in ui/widgets/task_card.py are
saturated accent borders, not fills, so they stay legible unchanged in
both modes (spec §49's "color meanings must remain understandable in
both modes")."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(37, 37, 38)
    base = QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    disabled_text = QColor(127, 127, 127)
    highlight = QColor(60, 110, 200)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipBase, text)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("red"))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("black"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def _light_palette() -> QPalette:
    palette = QPalette()
    window = QColor(240, 240, 240)
    base = QColor(255, 255, 255)
    text = QColor(20, 20, 20)
    disabled_text = QColor(150, 150, 150)
    highlight = QColor(60, 110, 200)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("red"))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def apply_system_theme(app: QApplication) -> None:
    is_dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    if is_dark:
        app.setStyle("Fusion")
        app.setPalette(_dark_palette())


def apply_theme(app: QApplication, preference: str = "system") -> None:
    """Phase 6 Settings "Appearance" control. `preference` is one of
    "system" (default — OS-driven via `apply_system_theme`), "light", or
    "dark" (explicit override). Called at startup (main.py, after reading
    the stored setting) and live from Settings' save handler, so a running
    app reflects a change immediately without a restart."""
    if preference == "dark":
        app.setStyle("Fusion")
        app.setPalette(_dark_palette())
    elif preference == "light":
        app.setStyle("Fusion")
        app.setPalette(_light_palette())
    else:
        app.setPalette(app.style().standardPalette())
        apply_system_theme(app)
