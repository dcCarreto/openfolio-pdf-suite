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

    # Os ícones ficam no texto secundário; o texto principal fica para o que está sob o mouse.
    assert dark == ("#161826", "#a9adbf")
    assert light == ("#eceef4", "#4f5368")
    assert "#eceef4" in app.styleSheet() and "#161826" not in app.styleSheet()
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

    assert fill(chosen) == theme.TOKENS[key]["accent_fill"] != fill(plain)


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
    assert _window_color(app) == "#eceef4"
    assert Preferences(settings).theme() == theme.LIGHT

    # "Seguir o sistema" acompanha a troca feita no sistema com o app aberto.
    window.set_theme(theme.SYSTEM)
    monkeypatch.setattr(theme, "resolved_theme", lambda _theme: theme.DARK)
    window._on_system_color_scheme_changed(Qt.ColorScheme.Dark)
    assert _window_color(app) == "#161826"


def _luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """A razão de contraste da WCAG 2 entre duas cores #rrggbb."""
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("key", [theme.DARK, theme.LIGHT])
@pytest.mark.parametrize(
    "fore, back, minimum",
    [
        ("text", "panel", 12),
        ("text2", "panel", 7),
        ("text3", "panel", 4.8),
        ("text3", "field", 4.5),  # placeholder
        ("text2", "bg", 4.5),  # ícones e rótulos das barras
        ("accent_strong", "accent_fill", 4.5),  # o que está marcado, o botão principal
        ("on_accent", "accent", 4.5),
        ("accent", "field", 3),  # a borda de foco (componente de interface: 3:1)
        ("success", "success_fill", 4.5),
        ("danger", "danger_fill", 4.5),
        ("text", "success_fill", 4.5),
        ("text", "danger_fill", 4.5),
    ],
)
def test_text_and_states_pass_wcag_aa(key, fore, back, minimum):
    t = theme.TOKENS[key]
    assert contrast(t[fore], t[back]) >= minimum


def test_no_color_of_the_old_theme_is_left(app, tmp_path):
    from ui.main_window import MainWindow

    old = ["#1e1e1e", "#2c2c2e", "#3a3a3c", "#48484a", "#0a84ff", "#e8e8ed", "#dcdce1", "#007aff", "#0064d6"]
    MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    for key in (theme.DARK, theme.LIGHT):
        theme.apply_theme(app, key)
        sheet = app.styleSheet().lower()
        assert not [color for color in old if color in sheet]
        palette = app.palette()
        assert not [role for role in QPalette.ColorRole if role != QPalette.ColorRole.NColorRoles and palette.color(role).name() in old]


def test_inter_is_bundled_and_becomes_the_app_font(app):
    theme.apply_theme(app, theme.DARK)

    assert theme.load_fonts()
    assert app.font().families()[0] == "Inter"
    assert (theme._FONTS_DIR / "OFL.txt").is_file()


def test_animations_preference_defaults_on_and_is_remembered(tmp_path):
    prefs = Preferences(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    assert prefs.animations()
    prefs.set_animations(False)
    assert not Preferences(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)).animations()


def test_icons_follow_the_state(app):
    from PySide6.QtGui import QIcon

    theme.apply_theme(app, theme.DARK)
    t = theme.TOKENS[theme.DARK]
    icon = build_pages_icon()

    def color(mode, state=QIcon.State.Off):
        image = icon.pixmap(44, 44, mode, state).toImage()
        from collections import Counter

        found = Counter(
            image.pixelColor(x, y).name() for x in range(44) for y in range(44) if image.pixelColor(x, y).alpha() > 100
        )
        return found.most_common(1)[0][0]

    assert color(QIcon.Mode.Normal) == t["text2"]
    assert color(QIcon.Mode.Active) == t["text"]
    assert color(QIcon.Mode.Normal, QIcon.State.On) == t["accent_strong"]
    assert color(QIcon.Mode.Selected) == t["accent_strong"]
