"""Link para outro PDF com destino, PDF anexado aberto de um arquivo temporário e bloqueio de
cópia: nas outras saídas do conteúdo e com a senha de proprietário."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.generic import ArrayObject, Destination, DictionaryObject, Fit, FloatObject, NameObject, TextStringObject
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from reportlab.pdfgen import canvas as rl_canvas

from core.base import RestrictedPDFError, remember_password
from core.convert import ConvertToImages
from core.document_info import initial_view
from core.page_links import file_destination, page_links
from core.page_text import can_copy_text
from ui import theme
from ui.annotation_state import AnnotationState
from ui.document_session import ATTACHMENT_FOLDER_PREFIX, DocumentSession
from ui.main_window import MainWindow
from ui.preferences import Preferences, preferences, use_preferences
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import PdfViewer

RECT = (70, 695, 190, 715)


def _pdf(path, pages=5) -> str:
    canvas = rl_canvas.Canvas(str(path), pagesize=(612, 792))
    for number in range(pages):
        canvas.drawString(72, 700, f"pagina {number + 1}")
        canvas.showPage()
    canvas.save()
    return str(path)


def _with_named_destination(path, open_action=False) -> str:
    """O destino "capitulo" na página 4, a 500 de altura (o reportlab não grava destinos com nome)."""
    writer = PdfWriter(clone_from=path)
    writer.add_named_destination_object(
        Destination(TextStringObject("capitulo"), writer.pages[3].indirect_reference, Fit.xyz(top=500))
    )
    if open_action:
        writer.root_object[NameObject("/OpenAction")] = TextStringObject("capitulo")
    writer.write(path)
    return path


def _with_remote_link(path, file, destination) -> str:
    writer = PdfWriter(clone_from=path)
    writer.add_annotation(
        0,
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in RECT]),
                NameObject("/A"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject("/GoToR"),
                        NameObject("/F"): TextStringObject(file),
                        NameObject("/D"): destination,
                    }
                ),
            }
        ),
    )
    writer.write(path)
    return path


def _xyz(page, top):
    return ArrayObject([FloatObject(page), NameObject("/XYZ"), FloatObject(0), FloatObject(top), FloatObject(0)])


def _first_link(path):
    document = pdfium.PdfDocument(path)
    page = document[0]
    try:
        return page_links(document, page, path, 0)[0]
    finally:
        page.close()
        document.close()


@pytest.fixture(autouse=True)
def _clean_preferences():
    previous = preferences()
    use_preferences(Preferences())
    yield
    use_preferences(previous)


def _open(path) -> PdfViewer:
    QApplication.instance() or QApplication([])
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.resize(800, 700)
    viewer.show()
    session.open(path)
    QApplication.processEvents()
    return viewer


# -- destino do link para outro PDF -----------------------------------------------


def test_a_file_link_keeps_its_page_and_height(tmp_path):
    other = _pdf(tmp_path / "outro.pdf")
    link = _first_link(_with_remote_link(_pdf(tmp_path / "doc.pdf"), "outro.pdf", _xyz(2, 300)))

    assert link.file == "outro.pdf" and link.target_page is None
    assert file_destination(other, link) == (2, 300)


def test_a_file_link_with_a_named_destination_looks_it_up_in_the_other_file(tmp_path):
    other = _with_named_destination(_pdf(tmp_path / "outro.pdf"))
    link = _first_link(_with_remote_link(_pdf(tmp_path / "doc.pdf"), "outro.pdf", TextStringObject("capitulo")))
    assert file_destination(other, link) == (3, 500)

    missing = _first_link(_with_remote_link(_pdf(tmp_path / "doc2.pdf"), "outro.pdf", TextStringObject("nao_existe")))
    assert file_destination(other, missing) is None


def test_a_pdf_can_ask_to_open_at_a_named_destination(tmp_path):
    view = initial_view(_with_named_destination(_pdf(tmp_path / "doc.pdf"), open_action=True))
    assert (view.page, view.top) == (3, 500)


def test_following_the_link_shows_the_page_it_asks_for(tmp_path):
    _pdf(tmp_path / "outro.pdf")
    viewer = _open(_with_remote_link(_pdf(tmp_path / "doc.pdf"), "outro.pdf", _xyz(2, 300)))

    viewer._follow_link(viewer._page_links(0)[0])
    QApplication.processEvents()

    assert viewer.session.source_path().endswith("outro.pdf") and viewer._current_page == 2
    viewer.go_back()  # Voltar traz para o começo do outro documento, onde ele abriu
    assert viewer._current_page == 0
    viewer.close_document()


def test_a_page_out_of_the_other_file_just_opens_it(tmp_path):
    _pdf(tmp_path / "outro.pdf", pages=2)
    viewer = _open(_with_remote_link(_pdf(tmp_path / "doc.pdf"), "outro.pdf", _xyz(40, 300)))

    viewer._follow_link(viewer._page_links(0)[0])

    assert viewer.session.source_path().endswith("outro.pdf") and viewer._current_page == 0
    viewer.close_document()


# -- PDF anexado ------------------------------------------------------------------


@pytest.fixture
def window(tmp_path, monkeypatch):
    theme.apply_theme(QApplication.instance() or QApplication([]), theme.DARK)
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield window
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.close()


def _with_attachment(tmp_path) -> str:
    inner = _pdf(tmp_path / "interno.pdf", pages=2)
    source = _pdf(tmp_path / "doc.pdf")
    writer = PdfWriter(clone_from=source)
    with open(inner, "rb") as file:
        writer.add_attachment("interno.pdf", file.read())
    writer.write(source)
    return source


def test_saving_an_attached_pdf_asks_where_and_then_uses_that_file(window, tmp_path, monkeypatch):
    doc = window.open_document(_with_attachment(tmp_path))
    panel = doc.viewer.side_panel
    panel._on_attachment_activated(panel.attachments_list.item(0))
    attached = window.document
    assert attached is not doc
    temporary = attached.session.source_path()
    assert attached.session.needs_save_as() and ATTACHMENT_FOLDER_PREFIX in temporary
    assert temporary not in window._preferences.recent_files()
    original = open(temporary, "rb").read()

    target = tmp_path / "guardado.pdf"
    suggestions = []

    def choose(_parent, _title, suggestion, _filter):
        suggestions.append(suggestion)
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    assert window.save_document()

    assert os.path.basename(suggestions[0]) == "interno.pdf"
    assert target.read_bytes() == original
    assert attached.session.source_path() == str(target) and not attached.session.needs_save_as()

    suggestions.clear()
    assert window.save_document()  # agora é um arquivo como outro qualquer: não pergunta
    assert suggestions == []


def test_cancelling_the_save_of_an_attached_pdf_keeps_it_open_and_unsaved(window, tmp_path, monkeypatch):
    doc = window.open_document(_with_attachment(tmp_path))
    panel = doc.viewer.side_panel
    panel._on_attachment_activated(panel.attachments_list.item(0))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))

    assert not window.save_document()
    assert window.document.session.needs_save_as()


def test_opening_the_same_attachment_twice_returns_to_its_tab(window, tmp_path):
    doc = window.open_document(_with_attachment(tmp_path))
    panel = doc.viewer.side_panel
    panel._on_attachment_activated(panel.attachments_list.item(0))
    count = len(window.documents())
    window.tabs.setCurrentWidget(doc)

    panel._on_attachment_activated(panel.attachments_list.item(0))

    assert len(window.documents()) == count and window.document is not doc


def test_a_user_folder_with_the_same_name_is_not_taken_for_a_temporary_copy(tmp_path):
    folder = tmp_path / f"{ATTACHMENT_FOLDER_PREFIX}meu"
    folder.mkdir()
    session = DocumentSession()
    session.open(_pdf(folder / "doc.pdf", pages=1))
    assert not session.needs_save_as()


# -- bloqueio de cópia ------------------------------------------------------------


def _locked(tmp_path) -> str:
    source = _pdf(tmp_path / "doc.pdf", pages=2)
    writer = PdfWriter(clone_from=source)
    writer.encrypt(
        user_password="", owner_password="dono", permissions_flag=UserAccessPermissions.PRINT, algorithm="AES-256"
    )
    writer.write(source)
    return source


def test_exporting_pages_as_images_follows_the_permission_of_the_author(tmp_path):
    locked = _locked(tmp_path)
    with pytest.raises(RestrictedPDFError):
        ConvertToImages().run(locked, str(tmp_path / "saida"))

    remember_password(locked, "dono")
    assert len(ConvertToImages().run(locked, str(tmp_path / "saida"))) == 2


def test_the_owner_password_frees_the_copy_in_the_viewer(tmp_path):
    locked = _locked(tmp_path)
    remember_password(locked, "dono")
    viewer = _open(locked)

    assert can_copy_text(viewer._document)
    QApplication.clipboard().setText("antes")
    viewer.select_all_text()
    viewer.copy_selected_text()
    assert "pagina 2" in QApplication.clipboard().text()
    menu = viewer._context_menu(viewer._page_labels[0].mapToGlobal(QPoint(5, 5)))
    assert any(action.text() == "Copiar" for action in menu.actions())
    viewer.close_document()
