"""Testes do sistema de tradução (ui/i18n.py) e da troca de idioma na janela principal."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QListWidget

from ui import i18n
from ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def _reset_language():
    """Garante que cada teste comece e termine com o idioma padrão (pt_BR)."""
    i18n.set_language(i18n.PT_BR)
    yield
    i18n.set_language(i18n.PT_BR)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_default_language_is_pt_br():
    assert i18n.get_language() == i18n.PT_BR


def test_tr_is_identity_in_pt_br():
    assert i18n.tr("Mesclar") == "Mesclar"
    assert i18n.tr("texto sem tradução cadastrada") == "texto sem tradução cadastrada"


def test_tr_translates_in_en_us():
    i18n.set_language(i18n.EN_US)
    assert i18n.tr("Mesclar") == "Merge"
    assert i18n.tr("Comprimir") == "Compress"


def test_tr_falls_back_to_source_text_when_missing():
    i18n.set_language(i18n.EN_US)
    assert i18n.tr("um texto qualquer sem tradução") == "um texto qualquer sem tradução"


def test_set_language_rejects_invalid_value():
    with pytest.raises(ValueError):
        i18n.set_language("fr_FR")


def test_set_language_emits_signal_only_on_change():
    calls = []
    i18n.language_changed.changed.connect(lambda: calls.append(1))

    i18n.set_language(i18n.PT_BR)  # já é o idioma atual: não deve emitir
    assert len(calls) == 0

    i18n.set_language(i18n.EN_US)
    assert len(calls) == 1

    i18n.set_language(i18n.EN_US)  # já é o idioma atual: não deve emitir de novo
    assert len(calls) == 1


def test_main_window_rebuilds_sidebar_on_language_change():
    _app()
    window = MainWindow()
    original_session = window.session

    sidebar = window.findChild(QListWidget, "sidebar")
    assert sidebar.item(1).text() == "Mesclar"

    sidebar.setCurrentRow(4)  # Comprimir
    i18n.set_language(i18n.EN_US)

    # A sessão do documento aberto precisa sobreviver ao rebuild da UI.
    assert window.session is original_session

    sidebar = window.findChild(QListWidget, "sidebar")
    assert sidebar.item(1).text() == "Merge"
    assert sidebar.item(4).text() == "Compress"
    assert sidebar.currentRow() == 4  # preserva a seção selecionada

    i18n.set_language(i18n.PT_BR)
    sidebar = window.findChild(QListWidget, "sidebar")
    assert sidebar.item(1).text() == "Mesclar"

    window.close()


def test_core_messages_are_translated_with_their_values():
    from core.base import require_valid_page_index

    i18n.set_language(i18n.EN_US)
    with pytest.raises(ValueError) as error:
        require_valid_page_index(3, 7, label="Página de destino")

    assert str(error.value) == "Página de destino 8 não existe: o documento tem 3 página(s)."
    assert i18n.error_text(error.value) == "Target page 8 does not exist: the document has 3 page(s)."


def test_fixed_core_errors_are_translated_too():
    i18n.set_language(i18n.EN_US)

    assert i18n.error_text(ValueError("Senha incorreta.")) == "Wrong password."
    assert i18n.error_text(OSError(2, "No such file")) == "[Errno 2] No such file"


def test_qt_standard_buttons_follow_the_app_language():
    from PySide6.QtCore import QCoreApplication

    app = _app()
    i18n.install_qt_translator(app)
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancelar"

    i18n.set_language(i18n.EN_US)
    i18n.install_qt_translator(app)
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancel"
