"""O AppImage no menu de aplicativos do Linux (ui/desktop_integration.py)."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from ui import desktop_integration


@pytest.fixture
def appimage(tmp_path, monkeypatch):
    """Como rodando de um AppImage: $APPIMAGE, o AppDir montado e a pasta de dados do usuário."""
    path = tmp_path / "Baixados" / "OpenFolio PDF Suite.AppImage"
    path.parent.mkdir()
    path.write_bytes(b"")
    appdir = tmp_path / "montado"
    appdir.mkdir()
    (appdir / "openfolio-pdf-suite.png").write_bytes(b"png")
    monkeypatch.setenv("APPIMAGE", path.as_posix())  # no Linux, sem barras invertidas
    monkeypatch.setenv("APPDIR", str(appdir))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setattr(desktop_integration.shutil, "which", lambda _name: None)
    return path.as_posix()


def test_exec_quotes_the_path_as_the_desktop_entry_spec_says():
    assert desktop_integration.exec_argument("/home/ana/Meus PDFs/app.AppImage") == '"/home/ana/Meus PDFs/app.AppImage"'
    # `$` e `"` com uma barra; a barra, dobrada pelo escape de string; `%` dobrado.
    assert desktop_integration.exec_argument('/a/$x"y%z') == r'"/a/\\$x\\"y%%z"'
    assert desktop_integration.exec_argument("/a/b\\c") == r'"/a/b\\\\c"'


def test_the_entry_points_to_the_appimage_follows_it_and_goes_away(appimage, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert desktop_integration.appimage_path() == appimage
    assert not desktop_integration.is_integrated()

    desktop_integration.integrate(appimage)

    entry = desktop_integration.desktop_file().read_text(encoding="utf-8")
    assert f'Exec="{appimage}" %F' in entry and f"TryExec={appimage}" in entry
    assert "MimeType=application/pdf;" in entry
    assert desktop_integration.icon_file().read_bytes() == b"png"  # copiado: o AppDir some

    moved = (tmp_path / "app.AppImage").as_posix()
    desktop_integration.follow(moved)
    assert f'Exec="{moved}" %F' in desktop_integration.desktop_file().read_text(encoding="utf-8")

    desktop_integration.remove()
    assert not desktop_integration.is_integrated() and not desktop_integration.icon_file().exists()
    desktop_integration.follow(appimage)  # sem entrada, não cria nenhuma
    assert not desktop_integration.is_integrated()


def test_outside_an_appimage_there_is_nothing_to_offer(monkeypatch):
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert desktop_integration.appimage_path() is None


def test_the_app_asks_once_and_the_menu_toggles_the_entry(appimage, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop_integration, "appimage_path", lambda: appimage)  # sys.platform fica
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: asked.append(args) or QMessageBox.StandardButton.Yes)
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    try:
        window.offer_app_menu()
        assert len(asked) == 1 and desktop_integration.is_integrated()
        assert window._app_menu_action.isChecked()

        window.offer_app_menu()  # próxima execução: não pergunta de novo
        assert len(asked) == 1

        window._app_menu_action.setChecked(False)
        assert not desktop_integration.is_integrated()
    finally:
        window.close()
