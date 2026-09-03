"""Shared visual design tokens: spacing/radius constants, the category
color palette, and the global QSS stylesheet applied on top of the
existing light/dark QPalette (see ui/theme.py — this module does not
introduce a second theming mechanism, it only adds chrome/spacing on top
of whatever palette theme.py has already set).

Widget-specific dynamic styling (task card state-color stripe/selection
outline, the title-auto-fill marker, etc.) stays local to those widgets,
exactly as before — this module only owns what's common across the app.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

# --- Spacing / radius scale ---------------------------------------------

SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 18
SPACING_XL = 24

PAGE_MARGIN = 20        # outer margin for top-level panel layouts
RADIUS_LG = 10          # cards
RADIUS = 8              # buttons, sidebar rows, group boxes
RADIUS_SM = 6           # inputs, list items, pills

# --- Typography scale (used directly as widget-local stylesheets) ------

FONT_TITLE = "font-size: 14px; font-weight: 600;"
FONT_META = "font-size: 11px; font-weight: 400; color: palette(mid);"
FONT_SECTION_HEADER = (
    "font-size: 11px; font-weight: 700; color: palette(mid); "
    "letter-spacing: 1px;"
)

# --- Category accent palette ---------------------------------------------
# (light, dark) hex pairs — approved palette. Distinct hues spread across
# the wheel; used only as small accents (dot/pill), never as a card's
# whole background fill. A category outside this set (shouldn't normally
# happen — see config.settings.DEFAULT_CATEGORIES) falls back to a
# neutral gray dot rather than crashing.

CATEGORY_COLORS = {
    "Family": ("#D9527A", "#F0A0BB"),
    "Personal": ("#7C5CD1", "#B7A3F2"),
    "Work": ("#2E7FD6", "#8FBBF5"),
    "School": ("#C9821E", "#E8B75B"),
    "Health": ("#2E9E6B", "#7BD1A6"),
}
_FALLBACK_CATEGORY_COLOR = ("#9AA0A6", "#9AA0A6")

# The one accent blue used app-wide for focus/selection/checked states —
# same value ui/theme.py already uses for QPalette.Highlight in both
# light and dark palettes, kept here in RGB-tuple form so this module can
# build translucent tints of it for QSS (which has no color-mixing
# functions of its own).
_ACCENT_RGB = (60, 110, 200)
ACCENT_HEX = "#{:02x}{:02x}{:02x}".format(*_ACCENT_RGB)


def is_dark_active(app: QApplication = None) -> bool:
    """Whether the currently active QPalette is a dark one — inspects the
    live palette (the single source of truth theme.py already maintains)
    rather than tracking theme state separately."""
    app = app or QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def category_color(category: str, is_dark: bool) -> str:
    """Hex accent color for `category`, already picked for the given
    light/dark mode."""
    light, dark = CATEGORY_COLORS.get(category, _FALLBACK_CATEGORY_COLOR)
    return dark if is_dark else light


def make_category_dot(category: str, is_dark: bool, diameter: int = 9) -> QLabel:
    """A small filled circle QLabel for inline use next to a category
    name (task cards, list rows) — a minimal accent, not a colored block."""
    dot = QLabel()
    dot.setFixedSize(diameter, diameter)
    color = category_color(category, is_dark)
    dot.setStyleSheet(f"background: {color}; border-radius: {diameter // 2}px;")
    return dot


def category_icon(category: str, is_dark: bool, diameter: int = 10) -> QIcon:
    """Same accent dot, rendered as a QIcon for use in QComboBox/QListWidget
    items (e.g. the category picker in the task editor)."""
    pixmap = QPixmap(diameter, diameter)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(category_color(category, is_dark)))
    painter.drawEllipse(0, 0, diameter, diameter)
    painter.end()
    return QIcon(pixmap)


def _rgba(rgb, alpha: int) -> str:
    r, g, b = rgb
    return f"rgba({r}, {g}, {b}, {alpha})"


def accent_rgba(alpha: int) -> str:
    """A translucent tint of the one app-wide accent color, for subtle
    highlights (e.g. today's column in the week view) that need to stay
    an accent, not a block of saturated background."""
    return _rgba(_ACCENT_RGB, alpha)


def mark_primary(button) -> None:
    """Flags a button as the primary action on its screen (e.g. "Add
    Task", "Generate Week") so it gets a filled-accent look via the
    `QPushButton[primary="true"]` rule in build_stylesheet() — the same
    treatment a QDialogButtonBox's own default (Save/OK) button gets
    automatically via `:default`, for buttons that live outside a dialog
    and so have no such built-in default-button concept. Deliberately
    sparing — one clear primary action per screen, not decoration."""
    button.setProperty("primary", True)


# A single translucent-accent overlay for the task editor's "this field
# was auto-filled from the title" marker (see task_editor.py's
# `_set_auto_marker`) — one alpha-blended value that reads as a subtle
# highlight against either a light or a dark field background, so it
# doesn't need a separate light/dark variant like the opaque category
# colors do.
AUTO_FILL_TINT = f"background-color: {accent_rgba(35)}; border: 1px solid {accent_rgba(110)};"


def style_form(form) -> None:
    """Generous, consistent spacing for a QFormLayout — used by every
    dialog in the app (task editor, project/settings forms) instead of
    each picking its own margins ad hoc."""
    form.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
    form.setVerticalSpacing(SPACING_MD)
    form.setHorizontalSpacing(SPACING_MD)


def build_stylesheet(is_dark: bool) -> str:
    """The app-wide QSS layer: buttons/inputs/lists/sidebar chrome, corner
    radii, hover/pressed states, generous padding. Built from the current
    palette via `palette(...)` wherever possible so it automatically
    tracks whatever QPalette ui/theme.py has applied — the handful of
    values that QSS can't derive from the palette alone (hover/pressed
    overlays, borders, the selection tint) are the only ones computed
    here per light/dark."""
    border = "rgba(255, 255, 255, 35)" if is_dark else "rgba(0, 0, 0, 45)"
    hover_overlay = "rgba(255, 255, 255, 18)" if is_dark else "rgba(0, 0, 0, 10)"
    pressed_overlay = "rgba(255, 255, 255, 28)" if is_dark else "rgba(0, 0, 0, 18)"
    selection_tint = _rgba(_ACCENT_RGB, 40)
    accent = f"rgb{_ACCENT_RGB}"
    accent_color = QColor(*_ACCENT_RGB)
    accent_hover = accent_color.lighter(112).name()
    accent_pressed = accent_color.darker(112).name()

    return f"""
        QPushButton {{
            background: palette(button);
            border: 1px solid {border};
            border-radius: {RADIUS}px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{ background: {hover_overlay}; }}
        QPushButton:pressed {{ background: {pressed_overlay}; }}
        QPushButton:disabled {{ color: palette(mid); }}

        QPushButton:default, QPushButton[primary="true"] {{
            background: {accent};
            border: 1px solid {accent};
            color: white;
            font-weight: 600;
        }}
        QPushButton:default:hover, QPushButton[primary="true"]:hover {{ background: {accent_hover}; }}
        QPushButton:default:pressed, QPushButton[primary="true"]:pressed {{ background: {accent_pressed}; }}

        QCheckBox {{ spacing: 8px; padding: 2px 0; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border-radius: 4px;
            border: 1px solid {border};
            background: palette(base);
        }}
        QCheckBox::indicator:checked {{
            background: {accent};
            border: 1px solid {accent};
        }}

        QLineEdit, QTextEdit, QComboBox, QDateEdit, QSpinBox {{
            background: palette(base);
            border: 1px solid {border};
            border-radius: {RADIUS_SM}px;
            padding: 6px 10px;
            selection-background-color: {accent};
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
        QDateEdit:focus, QSpinBox:focus {{
            border: 1px solid {accent};
        }}
        QComboBox::drop-down {{ border: none; width: 22px; }}

        QListWidget {{
            background: palette(base);
            border: 1px solid {border};
            border-radius: {RADIUS_SM}px;
            outline: 0;
        }}
        QListWidget::item {{ padding: 6px 8px; border-radius: {RADIUS_SM}px; }}
        QListWidget::item:selected {{ background: {selection_tint}; color: palette(text); }}
        QListWidget::item:hover:!selected {{ background: {hover_overlay}; }}

        QListWidget#sidebar {{
            border: none;
            background: transparent;
            padding: {SPACING_MD}px {SPACING_SM}px;
        }}
        QListWidget#sidebar::item {{
            padding: 10px 14px;
            margin: 2px 0px;
            border-radius: {RADIUS}px;
            font-weight: 500;
        }}
        QListWidget#sidebar::item:selected {{
            background: {selection_tint};
            color: {accent};
            font-weight: 600;
        }}
        QListWidget#sidebar::item:hover:!selected {{ background: {hover_overlay}; }}

        QScrollArea {{ border: none; }}

        QToolButton {{ border: none; background: transparent; }}

        QGroupBox {{
            border: 1px solid {border};
            border-radius: {RADIUS}px;
            margin-top: 16px;
            padding-top: 12px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: palette(mid);
        }}
    """
