"""Temas visuais, limpos e inspirados no macOS: escuro (o padrão), claro ou o do sistema."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

DARK = "dark"
LIGHT = "light"
SYSTEM = "system"
THEMES = (DARK, LIGHT, SYSTEM)

_COLORS = {
    DARK: {
        "bg": "#1e1e1e",
        "panel": "#2c2c2e",
        "elevated": "#3a3a3c",
        "border": "#48484a",
        "text": "#f5f5f7",
        "muted": "#8e8e93",
        "accent": "#0a84ff",
        "accent_pressed": "#0064d6",
        "hover": "#46464a",
        "overlay": "255, 255, 255",  # realce de hover: claro sobre o escuro
    },
    LIGHT: {
        "bg": "#e8e8ed",
        "panel": "#ffffff",
        "elevated": "#dcdce1",
        "border": "#c4c4c9",
        "text": "#1c1c1e",
        "muted": "#6e6e73",
        "accent": "#007aff",
        "accent_pressed": "#0062cc",
        "hover": "#cfcfd4",
        "overlay": "0, 0, 0",
    },
}

_current = DARK

_FONT_FAMILY = '"SF Pro Text", "Helvetica Neue", "Segoe UI", sans-serif'

def _stylesheet(colors: dict) -> str:
    _BG, _PANEL, _ELEVATED, _BORDER = colors["bg"], colors["panel"], colors["elevated"], colors["border"]
    _TEXT, _TEXT_MUTED = colors["text"], colors["muted"]
    _ACCENT, _ACCENT_PRESSED = colors["accent"], colors["accent_pressed"]
    _HOVER, _OVERLAY = colors["hover"], colors["overlay"]
    return f"""
* {{
    font-family: {_FONT_FAMILY};
    font-size: 10.5pt;
    color: {_TEXT};
}}

QMainWindow, QWidget {{
    background-color: {_BG};
}}

QLabel {{
    background: transparent;
}}

QTabWidget::pane {{
    border: 1px solid {_BORDER};
    border-radius: 8px;
    top: -1px;
    background-color: {_PANEL};
}}

QTabBar::tab {{
    background: transparent;
    color: {_TEXT_MUTED};
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QTabBar::tab:selected {{
    background-color: {_PANEL};
    color: {_TEXT};
}}

QTabBar::tab:hover:!selected {{
    color: {_TEXT};
}}

QPushButton {{
    background-color: {_ELEVATED};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}

QPushButton:hover {{
    background-color: {_HOVER};
}}

QPushButton:pressed {{
    background-color: {_ACCENT_PRESSED};
    border-color: {_ACCENT_PRESSED};
    color: white;
}}

QPushButton:disabled {{
    color: {_TEXT_MUTED};
    background-color: {_PANEL};
    border-color: {_BORDER};
}}

QPushButton#flagButton {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 0;
}}

QPushButton#flagButton:hover {{
    background-color: rgba({_OVERLAY}, 20);
}}

QPushButton#flagButton:pressed {{
    background-color: rgba({_OVERLAY}, 35);
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {_PANEL};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {_ACCENT};
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {_ACCENT};
}}

QLineEdit:read-only {{
    color: {_TEXT_MUTED};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {_PANEL};
    border: 1px solid {_BORDER};
    selection-background-color: {_ACCENT};
    outline: none;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px;
    border: none;
}}

QListWidget {{
    background-color: {_PANEL};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    outline: none;
}}

QListWidget::item {{
    padding: 4px 6px;
    border-radius: 4px;
}}

QListWidget::item:selected {{
    background-color: {_ACCENT};
    color: white;
}}

QListWidget::item:hover:!selected {{
    background-color: {_ELEVATED};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {_ELEVATED};
    border-radius: 5px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {_BORDER};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {_ELEVATED};
    border-radius: 5px;
    min-width: 24px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QMessageBox {{
    background-color: {_PANEL};
}}

QLabel#pageTitle {{
    font-size: 17pt;
    font-weight: 600;
}}

QLabel#pageSubtitle {{
    font-size: 10pt;
    color: {_TEXT_MUTED};
}}

QWidget#documentNotice {{
    background-color: {_ELEVATED};
    border-bottom: 1px solid {_BORDER};
}}

QPushButton#pageIndicatorButton {{
    background: transparent;
    border: none;
    padding: 0 4px;
}}

QListWidget#sidebar {{
    background-color: {_PANEL};
    border: none;
    border-right: 1px solid {_BORDER};
    border-radius: 0;
    padding: 8px 0;
    font-size: 11pt;
}}

QListWidget#sidebar::item {{
    padding: 10px 18px;
    border-radius: 0;
    margin: 0;
    border-left: 3px solid transparent;
}}

QListWidget#sidebar::item:selected {{
    background-color: {_ELEVATED};
    color: {_TEXT};
    border-left: 3px solid {_ACCENT};
}}

QListWidget#sidebar::item:hover:!selected {{
    background-color: rgba({_OVERLAY}, 12);
}}

QMenuBar {{
    background-color: {_PANEL};
    border-bottom: 1px solid {_BORDER};
    padding: 2px 4px;
}}

QMenuBar::item {{
    padding: 4px 10px;
    background: transparent;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {_ELEVATED};
}}

QMenu {{
    background-color: {_PANEL};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {_ACCENT};
    color: white;
}}

QMenu::separator {{
    height: 1px;
    background: {_BORDER};
    margin: 4px 0;
}}

QStatusBar {{
    background-color: {_PANEL};
    border-top: 1px solid {_BORDER};
    color: {_TEXT_MUTED};
}}
"""


def _palette(colors: dict) -> QPalette:
    palette = QPalette()
    roles = QPalette.ColorRole
    for role, key in (
        (roles.Window, "bg"),
        (roles.WindowText, "text"),
        (roles.Base, "panel"),
        (roles.AlternateBase, "elevated"),
        (roles.ToolTipBase, "panel"),
        (roles.ToolTipText, "text"),
        (roles.Text, "text"),
        (roles.Button, "elevated"),
        (roles.ButtonText, "text"),
        (roles.Link, "accent"),
        (roles.Highlight, "accent"),
        (roles.PlaceholderText, "muted"),
    ):
        palette.setColor(role, QColor(colors[key]))
    palette.setColor(roles.HighlightedText, QColor("white"))
    for role in (roles.Text, roles.ButtonText, roles.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["muted"]))
    return palette


def resolved_theme(theme: str) -> str:
    """DARK ou LIGHT: SYSTEM vira o esquema de cores do sistema (escuro se ele não disser)."""
    if theme == SYSTEM:
        scheme = QGuiApplication.styleHints().colorScheme()
        return LIGHT if scheme == Qt.ColorScheme.Light else DARK
    return theme if theme in _COLORS else DARK


def current_theme() -> str:
    """O tema aplicado agora (DARK ou LIGHT)."""
    return _current


def apply_theme(app: QApplication, theme: str = DARK) -> None:
    """Aplica o tema a toda a aplicação, inclusive às janelas já abertas. Os ícones
    desenhados pelo app (`ui/icon_utils.py`) seguem a paleta sozinhos."""
    global _current
    _current = resolved_theme(theme)
    colors = _COLORS[_current]
    app.setStyle("Fusion")
    app.setPalette(_palette(colors))
    app.setStyleSheet(_stylesheet(colors))
    for window in app.topLevelWidgets():
        if window.isWindow() and window.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            apply_titlebar(window)


def apply_titlebar(window: QWidget) -> None:
    """No Windows, a barra de título nativa acompanha o tema (o DWM não segue a paleta do Qt)."""
    if sys.platform != "win32":
        return

    app = QApplication.instance()
    if app is not None and app.platformName() == "offscreen":
        return

    import ctypes

    hwnd = int(window.winId())
    value = ctypes.c_int(1 if _current == DARK else 0)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE varia por build do Windows
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
        )
        if result == 0:
            break
