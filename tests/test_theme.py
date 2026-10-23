"""Testes do tema claro, do escuro e de "seguir o sistema" (A14)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from ui import theme
from ui.preferences import Preferences
from ui.sidebar_icons import build_pages_icon


@pytest.fixture
def app():
    app = QApplication.instance() or QApplication([])
    yield app
    # O tema vale para o processo inteiro: os outros testes rodam sem ele, como antes.
    app.setStyleSheet("")
    app.setPalette(app.style().standardPalette())
    theme._current = theme.DARK


def _window_color(app) -> str:
    return app.palette().color(QPalette.ColorRole.Window).name()


def _icon_color(icon) -> str:
    from collections import Counter

    image = icon.pixmap(44, 44).toImage()
    colors = Counter(
        image.pixelColor(x, y).name() for x in range(44) for y in range(44) if image.pixelColor(x, y).alpha() > 200
    )
    return colors.most_common(1)[0][0]  # a do traço; a borda antisserrilhada varia um pouco


def test_light_and_dark_change_palette_stylesheet_and_icons_already_built(app):
    icon = build_pages_icon()

    theme.apply_theme(app, theme.DARK)
    dark = (_window_color(app), _icon_color(icon))
    theme.apply_theme(app, theme.LIGHT)
    light = (_window_color(app), _icon_color(icon))

    assert dark == ("#1e1e1e", "#f5f5f7")
    assert light == ("#e8e8ed", "#1c1c1e")
    assert "#e8e8ed" in app.styleSheet() and "#1e1e1e" not in app.styleSheet()
    assert theme.current_theme() == theme.LIGHT


@pytest.mark.parametrize("key", [theme.DARK, theme.LIGHT])
def test_the_chosen_tool_button_stands_out(app, key):
    from PySide6.QtWidgets import QPushButton

    theme.apply_theme(app, key)
    plain, chosen = QPushButton("Realce"), QPushButton("Realce")
    for button in (plain, chosen):
        button.setCheckable(True)
        button.resize(120, 30)
    chosen.setChecked(True)

    def fill(button):
        return button.grab().toImage().pixelColor(6, 15).name()  # dentro da borda, fora do texto

    assert fill(chosen) == theme._COLORS[key]["accent"] != fill(plain)


def test_follow_the_system_uses_its_color_scheme(app, monkeypatch):
    class Hints:
        scheme = Qt.ColorScheme.Light

        def colorScheme(self):
            return self.scheme

    hints = Hints()
    monkeypatch.setattr(theme.QGuiApplication, "styleHints", staticmethod(lambda: hints))

    assert theme.resolved_theme(theme.SYSTEM) == theme.LIGHT
    hints.scheme = Qt.ColorScheme.Dark
    assert theme.resolved_theme(theme.SYSTEM) == theme.DARK
    hints.scheme = Qt.ColorScheme.Unknown
    assert theme.resolved_theme(theme.SYSTEM) == theme.DARK  # sistema que não diz: o padrão


def test_theme_preference_is_remembered(tmp_path):
    prefs = Preferences(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    assert prefs.theme() == theme.DARK
    prefs.set_theme(theme.SYSTEM)
    assert Preferences(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)).theme() == theme.SYSTEM
    prefs.set_theme("roxo")
    assert prefs.theme() == theme.DARK


def test_view_menu_switches_and_saves_the_theme(app, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    assert window._theme_actions[theme.DARK].isChecked()

    window._theme_actions[theme.LIGHT].trigger()

    assert window._theme_actions[theme.LIGHT].isChecked()
    assert _window_color(app) == "#e8e8ed"
    assert Preferences(settings).theme() == theme.LIGHT

    # "Seguir o sistema" acompanha a troca feita no sistema com o app aberto.
    window.set_theme(theme.SYSTEM)
    monkeypatch.setattr(theme, "resolved_theme", lambda _theme: theme.DARK)
    window._on_system_color_scheme_changed(Qt.ColorScheme.Dark)
    assert _window_color(app) == "#1e1e1e"
