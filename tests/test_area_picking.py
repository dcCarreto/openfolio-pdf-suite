"""Posicionar pelo visualizador (M04): campos de formulário, corte e selo da assinatura."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader, PdfWriter
from PySide6.QtWidgets import QApplication

from ui.annotation_state import AnnotationState
from ui.area_pick_state import AreaPickState
from ui.document_session import DocumentSession
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import PdfViewer


def _pdf(path, rotate=0):
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    if rotate:
        page.rotate(rotate)
    writer.write(str(path))
    return str(path)


def _setup(tmp_path, page_class, rotate=0):
    QApplication.instance() or QApplication([])
    session = DocumentSession()
    state = AreaPickState()
    viewer = PdfViewer(session, AnnotationState(), RedactionState(), area_pick_state=state)
    session.open(_pdf(tmp_path / "doc.pdf", rotate))
    page = page_class(session, area_pick_state=state)
    state.set_active_page(page)
    return viewer, page, state


def _drag(viewer, start=(20, 20), end=(140, 80)):
    viewer._on_canvas_pressed(*start)
    viewer._on_canvas_released(*end)
    return viewer._widget_point_to_pdf(0, *start), viewer._widget_point_to_pdf(0, *end)


def test_dragging_sets_the_form_field_position_and_size(tmp_path):
    from ui.pages.form_fields_page import FormFieldsPage

    viewer, page, state = _setup(tmp_path, FormFieldsPage)

    (x1, y1), (x2, y2) = _drag(viewer)

    assert page.x_spin.value() == pytest.approx(min(x1, x2), abs=0.01)
    assert page.y_spin.value() == pytest.approx(min(y1, y2), abs=0.01)
    assert page.width_spin.value() == pytest.approx(abs(x2 - x1), abs=0.02)
    assert page.height_spin.value() == pytest.approx(abs(y2 - y1), abs=0.02)
    assert len(state.areas()) == 1  # o campo aparece desenhado na página


def test_dragging_places_the_selected_radio_option(tmp_path):
    from ui.pages.form_fields_page import FormFieldsPage

    viewer, page, _state = _setup(tmp_path, FormFieldsPage)
    page.mode_combo.setCurrentIndex(1)  # grupo de opções
    page.radio_table.setCurrentCell(0, 0)

    (x1, y1), (x2, y2) = _drag(viewer)

    assert float(page.radio_table.item(0, 2).text()) == pytest.approx(min(x1, x2), abs=0.1)
    assert float(page.radio_table.item(0, 3).text()) == pytest.approx(min(y1, y2), abs=0.1)
    assert page.radio_table.currentRow() == 1  # a próxima opção já fica selecionada


@pytest.mark.parametrize("rotate", [0, 90])
def test_dragging_the_area_to_keep_sets_the_crop_margins(tmp_path, rotate):
    from core.crop import CropPages
    from core.geometry import PageGeometry
    from ui.pages.crop_page import CropPage

    viewer, page, _state = _setup(tmp_path, CropPage, rotate)

    _drag(viewer, start=(30, 40), end=(200, 160))

    margins = [spin.value() for spin in (page.left_spin, page.bottom_spin, page.right_spin, page.top_spin)]
    assert all(margin > 0 for margin in margins)
    output = tmp_path / "cortado.pdf"
    CropPages().run(page.session.path(), str(output), *margins)
    geometry = PageGeometry.from_pypdf_page(PdfReader(str(output)).pages[0])
    scale = viewer._scale
    assert geometry.width == pytest.approx(170 / scale, abs=1)  # o que fica é a área arrastada
    assert geometry.height == pytest.approx(120 / scale, abs=1)


def test_dragging_chooses_the_signature_stamp_area(tmp_path):
    from ui.pages.signature_page import _CUSTOM_POSITION, SignaturePage

    viewer, page, state = _setup(tmp_path, SignaturePage)

    _drag(viewer)

    assert page.position_combo.currentIndex() == _CUSTOM_POSITION
    assert page._stamp_area[0] == 0 and state.areas() == [page._stamp_area]


def test_signature_uses_the_marked_box(tmp_path):
    from core.signature import SignDocument

    source = _pdf(tmp_path / "doc.pdf")
    output = tmp_path / "assinado.pdf"
    box = (50.0, 60.0, 250.0, 120.0)

    SignDocument().run(source, str(output), signer_name="Ana", test_common_name="Ana", box=box)

    widget = next(
        ref.get_object() for ref in PdfReader(str(output)).pages[0]["/Annots"] if ref.get_object().get("/FT") == "/Sig"
    )
    assert [round(float(v)) for v in widget["/Rect"]] == [50, 60, 250, 120]


def test_signature_rejects_a_tiny_box(tmp_path):
    from core.signature import SignDocument

    with pytest.raises(ValueError, match="pequena"):
        SignDocument().run(
            _pdf(tmp_path / "doc.pdf"), str(tmp_path / "o.pdf"), signer_name="A", test_common_name="A", box=(0, 0, 5, 5)
        )
