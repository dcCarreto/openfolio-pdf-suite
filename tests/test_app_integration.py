"""Abrir com / linha de comando (M08, B39), arrastar e soltar (M06) e preferências (M07)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pypdf import PdfWriter
from PySide6.QtCore import QMimeData, QSettings, QUrl
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication

from ui import i18n
from ui.app_events import FileOpenFilter, pdf_paths_from_arguments
from ui.preferences import Preferences
from ui.widgets.file_list_editor import FileListEditor


def _app():
    return QApplication.instance() or QApplication([])


def _pdf(path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(str(path))
    return str(path)


def test_arguments_keep_only_existing_pdfs(tmp_path):
    pdf = _pdf(tmp_path / "contrato.pdf")
    (tmp_path / "notas.txt").write_text("x")

    paths = pdf_paths_from_arguments(["--debug", str(tmp_path / "notas.txt"), str(tmp_path / "sumiu.pdf"), pdf])

    assert paths == [os.path.abspath(pdf)]


def test_file_url_arguments_are_understood(tmp_path):
    pdf = _pdf(tmp_path / "com espaço.pdf")

    assert pdf_paths_from_arguments([QUrl.fromLocalFile(pdf).toString()]) == [os.path.abspath(pdf)]


def test_macos_file_open_event_opens_the_pdf(tmp_path):
    _app()
    opened = []
    pdf = _pdf(tmp_path / "doc.pdf")

    handled = FileOpenFilter(opened.append).eventFilter(None, QFileOpenEvent(pdf))

    assert handled and opened == [pdf]


class _FakeDrop:
    def __init__(self, paths):
        self._mime = QMimeData()
        self._mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        self.accepted = False

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def test_dropping_files_on_a_list_adds_only_the_accepted_types(tmp_path):
    _app()
    editor = FileListEditor(dialog_caption="x", file_filter="PDF (*.pdf)")
    pdf = _pdf(tmp_path / "a.pdf")
    (tmp_path / "b.png").write_bytes(b"png")
    event = _FakeDrop([pdf, str(tmp_path / "b.png")])

    editor.dropEvent(event)

    assert editor.paths() == [pdf] and event.accepted


def test_dropping_a_pdf_on_the_window_opens_it(tmp_path):
    from ui.main_window import MainWindow

    _app()
    window = MainWindow()
    pdf = _pdf(tmp_path / "solto.pdf")
    event = _FakeDrop([pdf])

    window.dragEnterEvent(event)
    assert event.accepted
    window.dropEvent(event)

    assert window.session.source_path() == os.path.abspath(pdf)
    window.close()


def test_recent_files_are_ordered_unique_and_existing(tmp_path):
    prefs = Preferences()
    files = [_pdf(tmp_path / f"{name}.pdf") for name in ("a", "b", "c")]
    for path in files:
        prefs.add_recent_file(path)
    prefs.add_recent_file(files[0])
    os.remove(files[1])

    assert prefs.recent_files() == [os.path.abspath(files[0]), os.path.abspath(files[2])]
    assert prefs.last_folder() == str(tmp_path)


def test_window_remembers_language_and_recent_files(tmp_path):
    from ui.main_window import MainWindow

    _app()
    settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    pdf = _pdf(tmp_path / "relatorio.pdf")
    window.session.open(pdf)
    i18n.set_language(i18n.EN_US)
    window.close()
    i18n.language_changed.changed.disconnect(window._on_language_changed)
    i18n.set_language(i18n.PT_BR)

    reopened = MainWindow(settings=settings)
    try:
        assert i18n.get_language() == i18n.EN_US
        reopened._fill_recent_menu()
        names = [action.text() for action in reopened._recent_menu.actions()]
        assert "relatorio.pdf" in names
    finally:
        reopened.close()
        i18n.set_language(i18n.PT_BR)
        settings.clear()
