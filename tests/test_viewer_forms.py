"""Formulários preenchidos no visualizador (A02): ListFormWidgets, FillFormFields e os
cliques na página."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader
from pypdf.generic import NameObject
from PySide6.QtWidgets import QApplication

from core.form_fields import FillFormFields, ListFormFields, ListFormWidgets
from tests.test_form_fields import _build_pdf_with_various_fields
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.redaction_state import RedactionState
from ui.tasks import wait_for_tasks
from ui.viewer.pdf_viewer import PdfViewer


def _values(path) -> dict[str, str]:
    return {field.name: field.value for field in ListFormFields().run(str(path))}


def test_list_form_widgets_gives_position_value_and_states(tmp_path):
    widgets = ListFormWidgets().run(_build_pdf_with_various_fields(tmp_path))

    summary = [(w.name, w.field_type, w.rect, w.value, w.on_state) for w in widgets]
    assert summary == [
        ("nome", "text", (50, 350, 250, 370), "", ""),
        ("aceite", "checkbox", (50, 300, 65, 315), "/Off", "/Yes"),
        ("estado", "dropdown", (50, 250, 250, 270), "SP", ""),
        ("sexo", "radio", (50, 200, 66, 216), "/M", "/M"),
        ("sexo", "radio", (100, 200, 116, 216), "/M", "/F"),
    ]
    assert widgets[2].options == [("SP", "SP"), ("RJ", "RJ")]


def test_fill_form_fields_writes_each_type(tmp_path):
    source = _build_pdf_with_various_fields(tmp_path)
    output = tmp_path / "preenchido.pdf"

    FillFormFields().run(
        source, str(output), {"nome": "José Conceição", "aceite": "/Yes", "estado": "RJ", "sexo": "/F", "outro": "x"}
    )

    assert _values(output) == {"nome": "José Conceição", "aceite": "/Yes", "estado": "RJ", "sexo": "/F"}
    # Cada opção do grupo liga só a própria aparência, e o /V do grupo é um nome.
    radios = [w for w in ListFormWidgets().run(str(output)) if w.name == "sexo"]
    reader = PdfReader(str(output))
    states = [annot.get_object()["/AS"] for annot in reader.pages[0]["/Annots"] if "/AS" in annot.get_object()]
    assert "/F" in states and "/M" not in states
    assert isinstance(reader.get_fields()["sexo"]["/V"], NameObject)
    assert [w.value for w in radios] == ["/F", "/F"]


@pytest.fixture
def viewer(tmp_path):
    QApplication.instance() or QApplication([])
    session = DocumentSession()
    session.open(_build_pdf_with_various_fields(tmp_path))
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.resize(800, 700)
    yield viewer
    viewer.close_document()


def _click(viewer, name: str, index: int = 0):
    widget = [w for w in viewer._form_widgets if w.name == name][index]
    center = viewer._user_rect_to_screen(widget.page_index, widget.rect).center()
    viewer._on_canvas_pressed(center.x(), center.y())
    viewer._on_canvas_released(center.x(), center.y())


def test_typing_in_a_text_field_creates_an_undoable_version(viewer):
    session = viewer.session
    _click(viewer, "nome")
    editor, _widget = viewer._field_editor
    editor.setText("Ana")
    editor.editingFinished.emit()

    assert wait_for_tasks()
    assert viewer._field_editor is None
    assert _values(session.path())["nome"] == "Ana"
    assert [w.value for w in viewer._form_widgets if w.name == "nome"] == ["Ana"]
    session.undo()
    assert _values(session.path())["nome"] == ""


def test_escape_closes_the_editor_without_filling(viewer):
    path = viewer.session.path()
    _click(viewer, "nome")
    editor, _widget = viewer._field_editor
    editor.setText("Ana")
    viewer._finish_field_edit(commit=False)

    assert viewer._field_editor is None
    assert viewer.session.path() == path


def test_clicks_toggle_checkbox_pick_radio_and_choose_option(viewer, monkeypatch):
    session = viewer.session
    _click(viewer, "aceite")
    assert wait_for_tasks()
    _click(viewer, "sexo", index=1)
    assert wait_for_tasks()
    monkeypatch.setattr(viewer, "_choose_option", lambda widget: "RJ")
    _click(viewer, "estado")
    assert wait_for_tasks()
    assert _values(session.path()) == {"nome": "", "aceite": "/Yes", "estado": "RJ", "sexo": "/F"}

    _click(viewer, "aceite")  # desmarca
    assert wait_for_tasks()
    assert _values(session.path())["aceite"] == "/Off"


def test_clicking_outside_fields_still_selects_text(viewer):
    viewer._on_canvas_pressed(5, 5)
    assert viewer._field_editor is None
    assert viewer._selection_start_pdf is not None
