"""Atualizações sem número de versão, com consentimento (A17 e a mudança para uma versão única)."""

import hashlib
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core import updates
from core.updates import INSTALLER_NAME, RELEASES_PAGE, installer_is_intact, newest_update, version_key
from ui.preferences import Preferences
from ui.update_dialog import UpdateDialog

_DOWNLOAD = f"{RELEASES_PAGE}/download"


def _release(tag, prerelease=False, draft=False, url=None, notes="", installer=None):
    """`installer`: (url, conteúdo) do instalador do Windows anexado à release."""
    release = {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": url or f"{RELEASES_PAGE}/tag/{tag}",
        "body": notes,
        "assets": [],
    }
    if installer is not None:
        download, data = installer
        release["assets"].append(
            {
                "name": INSTALLER_NAME,
                "browser_download_url": download,
                "size": len(data),
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        )
    return release


def test_identifiers_are_dates():
    order = ["2026.1.5", "2026.10.21", "2026.10.21.1", "2026.11.2", "v2027.1.1"]
    keys = [version_key(v) for v in order]
    assert keys == sorted(keys)
    assert version_key("2026.10.21") == version_key("v2026.10.21.0")
    assert version_key("nightly") is None


def test_newest_update_picks_the_latest_published_one():
    releases = [
        _release("v2026.11.2", notes="Novo: X"),
        _release("v2026.12.1", notes="Novo: Y"),
        _release("v2027.1.1", draft=True),
        _release("v2027.2.1", prerelease=True),  # build de teste
    ]
    update = newest_update(releases, "2026.10.21")
    assert update is not None
    assert (update.page, update.notes) == (f"{RELEASES_PAGE}/tag/v2026.12.1", "Novo: Y")
    assert newest_update(releases, "2026.12.1") is None
    assert newest_update({"message": "rate limited"}, "2026.10.21") is None
    assert newest_update([None, {"tag_name": None}, {"tag_name": "latest"}], "2026.10.21") is None


def test_only_pages_and_downloads_of_the_repository():
    update = newest_update(
        [_release("v2099.1.1", url="https://example.com/x", installer=("https://example.com/Setup.exe", b"x"))],
        "2026.10.21",
    )
    assert update is not None
    assert update.page == RELEASES_PAGE
    assert update.installer_url is None  # sem instalador confiável: só a página


def test_the_installer_needs_the_published_hash():
    data = b"instalador"
    with_hash = _release("v2099.1.1", installer=(f"{_DOWNLOAD}/v2099.1.1/{INSTALLER_NAME}", data))
    update = newest_update([with_hash], "2026.10.21")
    assert update is not None and update.installer_url and update.installer_size == len(data)

    without_hash = json.loads(json.dumps(with_hash))
    del without_hash["assets"][0]["digest"]
    assert newest_update([without_hash], "2026.10.21").installer_url is None


def test_installer_is_checked_by_size_and_sha256(tmp_path):
    data = b"instalador"
    update = newest_update([_release("v2099.1.1", installer=(f"{_DOWNLOAD}/x/{INSTALLER_NAME}", data))], "2026.10.21")
    path = tmp_path / INSTALLER_NAME
    path.write_bytes(data)
    assert installer_is_intact(path, update)
    path.write_bytes(b"instaladoR")  # mesmo tamanho, outro conteúdo
    assert not installer_is_intact(path, update)
    path.write_bytes(data[:-1])
    assert not installer_is_intact(path, update)


def test_check_on_start_is_off_until_enabled(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    assert not Preferences(settings).check_updates_on_start()
    Preferences(settings).set_check_updates_on_start(True)
    assert Preferences(settings).check_updates_on_start()
    assert not Preferences().check_updates_on_start()


def test_update_dialog_shows_what_changed_and_what_accepting_does():
    QApplication.instance() or QApplication([])
    update = updates.Update(page=RELEASES_PAGE, notes="## Novidades\n\n- Ferramenta **nova**")

    installing = UpdateDialog(update, can_install=True)
    assert "Ferramenta nova" in installing.notes.toPlainText()
    assert installing.accept_button.text() == "Baixar e instalar"
    assert UpdateDialog(update, can_install=False).accept_button.text() == "Abrir a página"


@pytest.fixture
def window(tmp_path):
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield window
    window.close()


def _check(window, monkeypatch, tmp_path, payload, manual, accept=True, installs=False):
    """Consulta um arquivo local no lugar da API do GitHub (o QtNetwork lê file://) e
    responde ao diálogo de atualização com `accept`."""
    path = tmp_path / "releases.json"
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(updates, "RELEASES_URL", QUrl.fromLocalFile(str(path)).toString())
    shown = []
    for name in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, name, lambda _p, _t, text, *_a, _name=name: shown.append((_name, text)))
    dialogs = []

    def exec_dialog(dialog):
        dialogs.append(dialog.notes.toPlainText())
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(UpdateDialog, "exec", exec_dialog)
    monkeypatch.setattr("ui.main_window._installs_updates", lambda: installs)
    monkeypatch.setattr("ui.main_window._update_folder", lambda: tmp_path / "update")
    opened, started = [], []
    monkeypatch.setattr("ui.main_window.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    monkeypatch.setattr("ui.main_window.QProcess.startDetached", lambda program, args: started.append((program, args)))
    monkeypatch.setattr(window, "close", lambda: True)
    assert window.check_for_updates(manual=manual)
    assert not window.check_for_updates(manual=manual)  # uma consulta por vez
    while window._update_reply is not None or getattr(window, "_update_download", None) is not None:
        QApplication.processEvents()
    return shown, dialogs, opened, started


def test_update_shows_what_changed_and_opens_the_page_when_accepted(window, monkeypatch, tmp_path):
    payload = json.dumps([_release("v2099.1.1", notes="- Nova ferramenta")])
    shown, dialogs, opened, started = _check(window, monkeypatch, tmp_path, payload, manual=False)
    assert dialogs == ["Nova ferramenta"]
    assert opened == [f"{RELEASES_PAGE}/tag/v2099.1.1"] and started == [] and shown == []


def test_nothing_happens_without_consent(window, monkeypatch, tmp_path):
    payload = json.dumps([_release("v2099.1.1", notes="- Nova ferramenta")])
    _shown, dialogs, opened, started = _check(window, monkeypatch, tmp_path, payload, manual=False, accept=False)
    assert len(dialogs) == 1 and opened == [] and started == []


def _local_installer(monkeypatch, tmp_path, data):
    """Um "instalador" servido por file://, no lugar do download do GitHub."""
    source = tmp_path / "publicado" / INSTALLER_NAME
    source.parent.mkdir()
    source.write_bytes(data)
    url = QUrl.fromLocalFile(str(source)).toString()
    monkeypatch.setattr(updates, "DOWNLOAD_PREFIX", url.rsplit("/", 1)[0] + "/")
    return url


def test_windows_downloads_checks_and_runs_the_installer(window, monkeypatch, tmp_path):
    data = b"MZ instalador de teste" * 1000
    url = _local_installer(monkeypatch, tmp_path, data)
    payload = json.dumps([_release("v2099.1.1", notes="- Nova", installer=(url, data))])

    shown, _dialogs, opened, started = _check(window, monkeypatch, tmp_path, payload, manual=True, installs=True)

    target = tmp_path / "update" / INSTALLER_NAME
    assert target.read_bytes() == data
    assert started == [(str(target), ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])]
    assert opened == [] and [name for name, _text in shown] == ["information"]


def test_a_download_that_does_not_match_is_not_installed(window, monkeypatch, tmp_path):
    url = _local_installer(monkeypatch, tmp_path, b"arquivo trocado no caminho")
    payload = json.dumps([_release("v2099.1.1", installer=(url, b"o instalador publicado"))])

    shown, _dialogs, _opened, started = _check(window, monkeypatch, tmp_path, payload, manual=True, installs=True)

    assert started == []
    assert [name for name, _text in shown] == ["warning"]
    assert not (tmp_path / "update").exists()


def test_automatic_check_is_silent_without_news_or_on_error(window, monkeypatch, tmp_path):
    old = json.dumps([_release("v2000.1.1")])
    assert _check(window, monkeypatch, tmp_path, old, manual=False) == ([], [], [], [])
    assert _check(window, monkeypatch, tmp_path, None, manual=False) == ([], [], [], [])


def test_manual_check_reports_up_to_date_and_errors(window, monkeypatch, tmp_path):
    shown, *_ = _check(window, monkeypatch, tmp_path, json.dumps([]), manual=True)
    assert shown == [("information", "O OpenFolio PDF Suite já está atualizado.")]
    shown, *_ = _check(window, monkeypatch, tmp_path, "<html>erro</html>", manual=True)
    assert [name for name, _text in shown] == ["warning"]


def test_help_menu_toggle_is_remembered(window):
    assert not window._update_on_start_action.isChecked()
    window._update_on_start_action.trigger()
    assert window._preferences.check_updates_on_start()
