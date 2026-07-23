"""Tema visual único: modo escuro, limpo, inspirado no macOS."""

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

_BG = "#1e1e1e"
_PANEL = "#2c2c2e"
_ELEVATED = "#3a3a3c"
_BORDER = "#48484a"
_TEXT = "#f5f5f7"
_TEXT_MUTED = "#8e8e93"
_ACCENT = "#0a84ff"
_ACCENT_PRESSED = "#0064d6"

_FONT_FAMILY = '"SF Pro Text", "Helvetica Neue", "Segoe UI", sans-serif'

_STYLESHEET = f"""
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
    background-color: #46464a;
}}

QPushButton:pressed {{
    background-color: {_ACCENT_PRESSED};
    border-color: {_ACCENT_PRESSED};
}}

QPushButton:disabled {{
    color: {_TEXT_MUTED};
    background-color: {_PANEL};
    border-color: {_BORDER};
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
    background-color: rgba(255, 255, 255, 12);
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


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(_BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(_PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(_ELEVATED))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(_ELEVATED))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.Link, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(_TEXT_MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(_TEXT_MUTED))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(_TEXT_MUTED)
    )
    return palette


def apply_theme(app: QApplication) -> None:
    """Aplica o tema escuro único, inspirado no macOS, a toda a aplicação."""
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setStyleSheet(_STYLESHEET)


def apply_dark_titlebar(window: QWidget) -> None:
    """No Windows, escurece a barra de título nativa (o DWM não segue a paleta do Qt)."""
    if sys.platform != "win32":
        return

    app = QApplication.instance()
    if app is not None and app.platformName() == "offscreen":
        return

    import ctypes

    hwnd = int(window.winId())
    value = ctypes.c_int(1)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE varia por build do Windows
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
        )
        if result == 0:
            break
