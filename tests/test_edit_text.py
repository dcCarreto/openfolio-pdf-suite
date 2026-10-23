"""Testes de core/edit_text.py: "edição" de texto por cobrir e reescrever."""

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas as rl_canvas

from core.base import EncryptedPDFError
from core.edit_text import EditTextArea, TextEditRect
from core.geometry import PageGeometry
from tests.conftest import HARD_PAGE_LAYOUTS


def _make_pdf_with_text(path, texts: list[str]) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 300))
    canvas.setFont("Helvetica", 16)
    y = 250
    for text in texts:
        canvas.drawString(40, y, text)
        y -= 40
    canvas.showPage()
    canvas.save()


def test_edit_text_area_replaces_old_text_with_new(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Valor antigo: 100", "Outra linha qualquer"])

    edit = TextEditRect(
        page_index=0, left=40, bottom=230, right=250, top=260, new_text="Valor novo: 200"
    )
    pages_edited = EditTextArea().run(str(path_in), str(path_out), [edit]).pages_edited

    assert pages_edited == 1
    after = PdfReader(str(path_out)).pages[0].extract_text()
    assert "Valor antigo" not in after
    assert "Valor novo: 200" in after


def test_edit_text_area_leaves_unmarked_pages_untouched(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"

    from pypdf import PdfReader as _R
    from pypdf import PdfWriter

    writer = PdfWriter()
    for text in ("Primeira pagina", "Segunda pagina sem edicao"):
        buffer_path = tmp_path / f"_{text[:4]}.pdf"
        _make_pdf_with_text(buffer_path, [text])
        writer.add_page(_R(str(buffer_path)).pages[0])
    with open(path_in, "wb") as f:
        writer.write(f)

    edit = TextEditRect(page_index=0, left=0, bottom=0, right=400, top=300, new_text="Editado")
    pages_edited = EditTextArea().run(str(path_in), str(path_out), [edit]).pages_edited

    assert pages_edited == 1
    reader = PdfReader(str(path_out))
    assert "Segunda pagina sem edicao" in reader.pages[1].extract_text()


def test_edit_text_area_with_no_edits_copies_document_unchanged(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Nada editado"])

    pages_edited = EditTextArea().run(str(path_in), str(path_out), []).pages_edited

    assert pages_edited == 0
    assert "Nada editado" in PdfReader(str(path_out)).pages[0].extract_text()


def test_edit_text_area_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_out = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        EditTextArea().run(str(encrypted_path), str(path_out), [])


def _text_box(path, text: str):
    document = pdfium.PdfDocument(str(path))
    try:
        textpage = document[0].get_textpage()
        searcher = textpage.search(text)
        index, count = searcher.get_next()
        boxes = [textpage.get_charbox(i) for i in range(index, index + count)]
        searcher.close()
        textpage.close()
    finally:
        document.close()
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


@pytest.mark.parametrize(("name", "layout"), list(HARD_PAGE_LAYOUTS.items()))
def test_edit_text_covers_the_right_area_on_hard_pages(make_text_pdf, tmp_path, name, layout):
    path_in = make_text_pdf(f"{name}.pdf", [(80, 650, "Valor antigo 100"), (80, 300, "Outra linha")], **layout)
    path_out = tmp_path / f"{name}_out.pdf"
    # A área é marcada como o usuário a arrasta na tela: cobre o texto antigo e é larga o
    # bastante, na horizontal da tela, para o texto novo (em páginas giradas o texto antigo
    # aparece em pé, numa faixa estreita).
    document = pdfium.PdfDocument(str(path_in))
    try:
        geometry_in = PageGeometry.from_pdfium_page(document[0])
    finally:
        document.close()
    v_left, v_bottom, v_right, v_top = geometry_in.user_rect_to_visual(_text_box(path_in, "Valor antigo 100"))
    visual_area = (v_left - 2, v_bottom - 4, max(v_right + 2, v_left + 160), max(v_top + 4, v_bottom + 20))
    left, bottom, right, top = geometry_in.visual_rect_to_user(visual_area)
    edit = TextEditRect(page_index=0, left=left, bottom=bottom, right=right, top=top, new_text="Valor novo 200")

    EditTextArea().run(str(path_in), str(path_out), [edit])

    page = PdfReader(str(path_out)).pages[0]
    text = page.extract_text()
    assert "Valor novo 200" in text
    assert "antigo" not in text

    # O texto antigo também não sobrevive na imagem: a área foi pintada nos próprios pixels.
    geometry_out = PageGeometry.from_pypdf_page(page)
    assert (geometry_out.width, geometry_out.height) == pytest.approx((geometry_in.width, geometry_in.height))
    image = page.images[0].image.convert("L")
    visual = geometry_in.user_rect_to_visual((edit.left, edit.bottom, edit.right, edit.top))
    assert image.crop(geometry_out.visual_rect_to_pixels(visual, image.width, image.height)).getextrema() == (255, 255)

    # O texto novo começa dentro da área coberta e corre "de pé", na direção em que se lê a
    # página na tela.
    new_left, new_bottom, new_right, new_top = geometry_out.user_rect_to_visual(
        _text_box(path_out, "Valor novo 200")
    )
    assert visual[0] - 1 <= new_left <= visual[2]
    assert visual[1] - 1 <= new_bottom and new_top <= visual[3] + 1
    assert new_right - new_left > new_top - new_bottom


def test_edit_text_rejects_invalid_page_index(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, ["Uma linha"])
    edit = TextEditRect(page_index=5, left=0, bottom=0, right=10, top=10, new_text="x")

    with pytest.raises(ValueError):
        EditTextArea().run(str(path_in), str(tmp_path / "out.pdf"), [edit])


def _boxed_edit(new_text, width=200, height=40, **options):
    return TextEditRect(page_index=0, left=100, bottom=150, right=100 + width, top=150 + height, new_text=new_text, **options)


def test_long_text_wraps_inside_the_area(tmp_path):
    path_in = tmp_path / "in.pdf"
    _make_pdf_with_text(path_in, ["Texto antigo"])
    path_out = tmp_path / "out.pdf"
    edit = _boxed_edit("uma frase comprida que precisa quebrar", width=120, height=60, font_size=10)

    result = EditTextArea().run(str(path_in), str(path_out), [edit])

    assert result.clipped == []
    left, bottom, right, top = _text_box(path_out, "quebrar")
    assert 100 <= left and right <= 220 and 150 <= bottom and top <= 210


def test_typed_line_breaks_become_new_lines(tmp_path):
    path_in = tmp_path / "in.pdf"
    _make_pdf_with_text(path_in, ["Texto antigo"])
    path_out = tmp_path / "out.pdf"

    EditTextArea().run(str(path_in), str(path_out), [_boxed_edit("Linha um\nLinha dois", height=40, font_size=10)])

    first, second = _text_box(path_out, "um"), _text_box(path_out, "dois")
    assert second[3] < first[1]  # a segunda linha fica abaixo da primeira


def test_text_that_does_not_fit_is_reported_and_not_hidden_in_the_file(tmp_path):
    path_in = tmp_path / "in.pdf"
    _make_pdf_with_text(path_in, ["Texto antigo"])
    path_out = tmp_path / "out.pdf"
    edit = _boxed_edit("primeira segunda terceira quarta quinta sexta", width=80, height=14, font_size=10)

    result = EditTextArea().run(str(path_in), str(path_out), [edit])

    assert result.clipped == [0]
    text = PdfReader(str(path_out)).pages[0].extract_text()
    assert "primeira" in text and "sexta" not in text  # nada vaza nem fica como texto escondido


def test_font_and_colors_are_applied(tmp_path):
    path_in = tmp_path / "in.pdf"
    _make_pdf_with_text(path_in, ["Texto antigo"])
    path_out = tmp_path / "out.pdf"
    edit = _boxed_edit("Łódź Ω", font="mono", text_color="ff0000", cover_color="00ff00")

    EditTextArea().run(str(path_in), str(path_out), [edit])

    page = PdfReader(str(path_out)).pages[0]
    assert "Łódź Ω" in page.extract_text()
    fonts = [str(font.get_object()["/BaseFont"]) for font in page["/Resources"]["/Font"].values()]
    assert any("DejaVuSansMono" in name for name in fonts)
    assert b"1 0 0 rg" in page.get_contents().get_data()
    image = page.images[0].image.convert("RGB")
    assert image.getpixel((int(image.width * 150 / 400), int(image.height * (300 - 155) / 300))) == (0, 255, 0)


def test_unknown_font_is_rejected(tmp_path):
    path_in = tmp_path / "in.pdf"
    _make_pdf_with_text(path_in, ["Texto antigo"])

    with pytest.raises(ValueError, match="Fonte"):
        EditTextArea().run(str(path_in), str(tmp_path / "out.pdf"), [_boxed_edit("x", font="comic")])
