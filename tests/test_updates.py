"""Verificação de atualização opt-in (A17)."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtWidgets import QApplication, QMessageBox

from core import updates
from core.updates import RELEASES_PAGE, newest_release, version_key
from ui.preferences import Preferences


def _release(tag, prerelease=False, draft=False, url=None):
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "html_url": url or f"{RELEASES_PAGE}/tag/{tag}"}


def test_version_order():
    order = ["0.2.0-beta.1", "0.2.0-beta.2", "0.2.0-rc.1", "0.2.0", "v0.2.1", "0.10.0", "1.0"]
    keys = [version_key(v) for v in order]
    assert keys == sorted(keys)
    assert version_key("0.2") == version_key("0.2.0")
    assert version_key("nightly") is None


def test_newest_release_picks_the_highest_newer_one():
    releases = [_release("v0.3.0"), _release("v0.4.0"), _release("v0.2.0"), _release("v0.5.0", draft=True)]
    assert newest_release(releases, "0.2.0") == ("0.4.0", f"{RELEASES_PAGE}/tag/v0.4.0")
    assert newest_release(releases, "0.4.0") is None
    assert newest_release([_release("v0.1.0")], "0.2.0") is None


def test_prereleases_only_for_prerelease_users():
    releases = [_release("v0.3.0-beta.1", prerelease=True), _release("v0.3.0-rc.1")]
    assert newest_release(releases, "0.2.0") is None
    assert newest_release(releases, "0.3.0-beta.1") == ("0.3.0-rc.1", f"{RELEASES_PAGE}/tag/v0.3.0-rc.1")


def test_only_opens_pages_of_the_repository():
    releases = [_release("v9.0.0", url="https://example.com/malware.exe")]
    assert newest_release(releases, "0.2.0") == ("9.0.0", RELEASES_PAGE)
    assert newest_release({"message": "rate limited"}, "0.2.0") is None
    assert newest_release([None, {"tag_name": None}, {"tag_name": "latest"}], "0.2.0") is None


def test_check_on_start_is_off_until_enabled(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    assert not Preferences(settings).check_updates_on_start()
    Preferences(settings).set_check_updates_on_start(True)
    assert Preferences(settings).check_updates_on_start()
    assert not Preferences().check_updates_on_start()


@pytest.fixture
def window(tmp_path):
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield window
    window.close()


def _check(window, monkeypatch, tmp_path, payload, manual):
    """Consulta um arquivo local no lugar da API do GitHub (o QtNetwork lê file://)."""
    path = tmp_path / "releases.json"
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(updates, "RELEASES_URL", QUrl.fromLocalFile(str(path)).toString())
    shown = []
    for name in ("information", "warning", "question"):
        monkeypatch.setattr(
            QMessageBox,
            name,
            lambda _parent, _title, text, *_args, _name=name: shown.append((_name, text)) or QMessageBox.StandardButton.Yes,
        )
    opened = []
    monkeypatch.setattr("ui.main_window.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    assert window.check_for_updates(manual=manual)
    assert not window.check_for_updates(manual=manual)  # uma consulta por vez
    while window._update_reply is not None:
        QApplication.processEvents()
    return shown, opened


def test_new_version_offers_the_download_page(window, monkeypatch, tmp_path):
    payload = json.dumps([_release("v99.0.0")])
    shown, opened = _check(window, monkeypatch, tmp_path, payload, manual=False)
    assert [name for name, _text in shown] == ["question"]
    assert "99.0.0" in shown[0][1]
    assert opened == [f"{RELEASES_PAGE}/tag/v99.0.0"]


def test_automatic_check_is_silent_without_news_or_on_error(window, monkeypatch, tmp_path):
    assert _check(window, monkeypatch, tmp_path, json.dumps([_release("v0.0.1")]), manual=False) == ([], [])
    assert _check(window, monkeypatch, tmp_path, None, manual=False) == ([], [])


def test_manual_check_reports_up_to_date_and_errors(window, monkeypatch, tmp_path):
    shown, _ = _check(window, monkeypatch, tmp_path, json.dumps([]), manual=True)
    assert [name for name, _text in shown] == ["information"]
    shown, _ = _check(window, monkeypatch, tmp_path, "<html>erro</html>", manual=True)
    assert [name for name, _text in shown] == ["warning"]


def test_help_menu_toggle_is_remembered(window):
    assert not window._update_on_start_action.isChecked()
    window._update_on_start_action.trigger()
    assert window._preferences.check_updates_on_start()
