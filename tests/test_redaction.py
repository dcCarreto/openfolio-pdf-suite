"""Testes de core/redaction.py: redação real (rasterização) e sanitização de PDFs."""

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    TextStringObject,
)
from reportlab.pdfgen import canvas as rl_canvas

from core import redaction
from core.base import EncryptedPDFError
from core.geometry import PageGeometry
from core.redaction import (
    FindSensitiveData,
    RedactDocument,
    RedactionRect,
    RedactionVerificationError,
    SanitizationVerificationError,
    SanitizeDocument,
    find_residual_risks,
)
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


def test_redact_wipes_all_text_from_marked_pages(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Segredo confidencial", "Outra linha qualquer"])

    before = PdfReader(str(path_in)).pages[0].extract_text()
    assert "Segredo" in before

    rect = RedactionRect(page_index=0, left=40, bottom=230, right=250, top=260)
    pages_redacted = RedactDocument().run(str(path_in), str(path_out), [rect])

    assert pages_redacted == 1
    after = PdfReader(str(path_out)).pages[0].extract_text()
    assert after.strip() == ""  # a página inteira virou imagem: nada de texto sobra


def test_redact_leaves_unmarked_pages_untouched(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"

    writer = PdfWriter()
    for text in ("Primeira pagina com dados", "Segunda pagina sem marcacao"):
        buffer_path = tmp_path / f"_{text[:4]}.pdf"
        _make_pdf_with_text(buffer_path, [text])
        writer.add_page(PdfReader(str(buffer_path)).pages[0])
    with open(path_in, "wb") as f:
        writer.write(f)

    rect = RedactionRect(page_index=0, left=0, bottom=0, right=400, top=300)
    pages_redacted = RedactDocument().run(str(path_in), str(path_out), [rect])

    assert pages_redacted == 1
    reader = PdfReader(str(path_out))
    assert reader.pages[0].extract_text().strip() == ""
    assert "Segunda pagina sem marcacao" in reader.pages[1].extract_text()


def test_redact_with_no_rects_copies_document_unchanged(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Nada marcado"])

    pages_redacted = RedactDocument().run(str(path_in), str(path_out), [])

    assert pages_redacted == 0
    assert "Nada marcado" in PdfReader(str(path_out)).pages[0].extract_text()


def test_redact_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_out = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        RedactDocument().run(str(encrypted_path), str(path_out), [])


def test_find_sensitive_data_locates_cpf_and_email(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(
        path_in, ["CPF: 123.456.789-00", "Contato: fulano@exemplo.com", "Sem dado sensivel aqui"]
    )

    rects = FindSensitiveData().run(str(path_in), kinds=["cpf", "email"])

    assert len(rects) == 2
    assert all(rect.page_index == 0 for rect in rects)
    assert all(rect.right > rect.left and rect.top > rect.bottom for rect in rects)


def test_find_sensitive_data_with_no_kinds_returns_empty(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, ["CPF: 123.456.789-00"])

    assert FindSensitiveData().run(str(path_in)) == []


def test_find_sensitive_data_supports_custom_regex(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, ["Processo numero PROC-2024-001"])

    rects = FindSensitiveData().run(str(path_in), custom_pattern=r"PROC-\d{4}-\d{3}")

    assert len(rects) == 1


def test_find_sensitive_data_rejects_invalid_regex(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, ["texto qualquer"])

    with pytest.raises(ValueError):
        FindSensitiveData().run(str(path_in), custom_pattern="(")


def test_find_sensitive_data_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        FindSensitiveData().run(str(encrypted_path), kinds=["email"])


def test_find_sensitive_data_rects_feed_into_redaction(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["CPF: 123.456.789-00", "Texto neutro"])

    rects = FindSensitiveData().run(str(path_in), kinds=["cpf"])
    pages_redacted = RedactDocument().run(str(path_in), str(path_out), rects)

    assert pages_redacted == 1
    after = PdfReader(str(path_out)).pages[0].extract_text()
    assert after.strip() == ""


def _pdf_with_hidden_data(path) -> None:
    src_text = str(path).replace(".pdf", "_src.pdf")
    _make_pdf_with_text(src_text, ["Conteudo visivel do documento"])

    quads = ArrayObject([FloatObject(v) for v in [40, 260, 200, 260, 40, 240, 200, 240]])
    writer = PdfWriter(clone_from=src_text)
    writer.add_metadata({"/Title": "Segredo Confidencial", "/Author": "Fulano de Tal"})
    writer.add_js('app.alert("oi");')
    writer.add_attachment("secreto.txt", b"dados sensiveis anexados")
    writer.add_annotation(
        page_number=0,
        annotation=Highlight(rect=(40, 240, 200, 260), quad_points=quads, highlight_color="ffeb3b"),
    )
    writer.add_annotation(
        page_number=0,
        annotation={
            "/Subtype": "/Link",
            "/Rect": [40, 200, 200, 220],
            "/A": {"/S": "/JavaScript", "/JS": 'app.alert("annotation js");'},
        },
    )
    with open(path, "wb") as f:
        writer.write(f)


def test_sanitize_default_removes_metadata_js_and_attachments_but_keeps_annotations(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_hidden_data(path_in)
    path_out = tmp_path / "out.pdf"

    SanitizeDocument().run(str(path_in), str(path_out))

    reader = PdfReader(str(path_out))
    assert reader.metadata.get("/Title") is None
    assert list(reader.attachments.keys()) == []
    assert reader.pages[0].get("/Annots") is not None
    assert "Conteudo visivel do documento" in reader.pages[0].extract_text()


def test_sanitize_removes_javascript_embedded_in_annotation_actions(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_hidden_data(path_in)
    path_out = tmp_path / "out.pdf"

    SanitizeDocument().run(str(path_in), str(path_out))

    reader = PdfReader(str(path_out))
    annots = [ref.get_object() for ref in reader.pages[0]["/Annots"]]
    link = next(a for a in annots if a["/Subtype"] == "/Link")

    # A anotação de link continua lá (remove_annotations=False por padrão), mas a ação de
    # JavaScript embutida nela foi removida — é exatamente o conteúdo que "sanitizar" promete
    # sempre eliminar, mesmo quando as anotações em si são preservadas.
    assert "/A" not in link
    assert any(a["/Subtype"] == "/Highlight" for a in annots)


def test_sanitize_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_out = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        SanitizeDocument().run(str(encrypted_path), str(path_out))


def test_sanitize_can_keep_metadata_and_remove_annotations(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_hidden_data(path_in)
    path_out = tmp_path / "out.pdf"

    SanitizeDocument().run(str(path_in), str(path_out), remove_metadata=False, remove_annotations=True)

    reader = PdfReader(str(path_out))
    assert reader.metadata.get("/Title") == "Segredo Confidencial"
    assert reader.pages[0].get("/Annots") is None
    assert list(reader.attachments.keys()) == []  # anexos são sempre removidos
    assert "Conteudo visivel do documento" in reader.pages[0].extract_text()


# -- redação em páginas "difíceis" (B01) e tarja gravada nos pixels (B50) --------------------

_RENDER_SCALE = 2.0


def _render(path, scale=_RENDER_SCALE):
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        return page.render(scale=scale).to_pil().convert("L"), PageGeometry.from_pdfium_page(page)
    finally:
        document.close()


def _crop(image, geometry: PageGeometry, visual_rect, inset: int = 0):
    x0, y0, x1, y1 = geometry.visual_rect_to_pixels(visual_rect, image.width, image.height)
    return image.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset))


def _text_box(path, text: str):
    """Caixa (espaço do usuário) de um trecho de texto, segundo o pdfium."""
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
def test_detected_data_is_really_gone_on_hard_pages(make_text_pdf, tmp_path, name, layout):
    path_in = make_text_pdf(
        f"{name}.pdf", [(80, 650, "CPF 123.456.789-09"), (80, 300, "Texto que fica")], **layout
    )
    path_out = tmp_path / f"{name}_out.pdf"

    rects = FindSensitiveData().run(str(path_in), kinds=["cpf"])
    assert len(rects) == 1
    pages_redacted = RedactDocument().run(str(path_in), str(path_out), rects)
    assert pages_redacted == 1

    before, geometry_in = _render(path_in)
    after, geometry_out = _render(path_out)
    # A página redigida tem o mesmo tamanho e orientação visual da original.
    assert (geometry_out.width, geometry_out.height) == pytest.approx((geometry_in.width, geometry_in.height))

    cpf_visual = geometry_in.user_rect_to_visual(geometry_in.clip_user_rect(rects[0].as_rect()))
    assert _crop(before, geometry_in, cpf_visual).getextrema()[0] < 100  # havia texto ali
    # Agora é só preto — no render (descontando 1 px de borda, onde a suavização mistura a
    # tarja com o vizinho) e, sem tolerância nenhuma, na imagem embutida.
    assert _crop(after, geometry_out, cpf_visual, inset=1).getextrema()[1] < 60
    embedded = PdfReader(str(path_out)).pages[0].images[0].image.convert("L")
    assert _crop(embedded, geometry_out, cpf_visual).getextrema() == (0, 0)

    # O texto que não foi marcado continua visível no mesmo lugar (a página não ficou preta).
    kept_visual = geometry_in.user_rect_to_visual(_text_box(path_in, "Texto que fica"))
    low, high = _crop(after, geometry_out, kept_visual).getextrema()
    assert low < 100 and high > 200


def test_redaction_burns_the_area_into_the_embedded_image(make_text_pdf, tmp_path):
    # Antes, a tarja era um retângulo desenhado por cima da imagem — a imagem embutida
    # continuava com o CPF legível para qualquer extrator de imagens.
    path_in = make_text_pdf("doc.pdf", [(80, 650, "CPF 123.456.789-09")])
    path_out = tmp_path / "out.pdf"
    rects = FindSensitiveData().run(str(path_in), kinds=["cpf"])
    RedactDocument().run(str(path_in), str(path_out), rects)

    page = PdfReader(str(path_out)).pages[0]
    images = page.images
    assert len(images) == 1
    image = images[0].image.convert("L")
    geometry = PageGeometry.from_pypdf_page(page)
    visual = geometry.user_rect_to_visual(rects[0].as_rect())
    assert _crop(image, geometry, visual).getextrema() == (0, 0)


def test_redaction_is_not_saved_when_verification_fails(make_text_pdf, tmp_path, monkeypatch):
    path_in = make_text_pdf("doc.pdf", [(80, 650, "CPF 123.456.789-09")])
    path_out = tmp_path / "out.pdf"
    rects = FindSensitiveData().run(str(path_in), kinds=["cpf"])
    # Simula um defeito que deixasse de pintar a área: a verificação tem que barrar.
    monkeypatch.setattr(redaction, "fill_visual_rects", lambda *args, **kwargs: None)

    with pytest.raises(RedactionVerificationError):
        RedactDocument().run(str(path_in), str(path_out), rects)

    assert not path_out.exists()
    assert not list(tmp_path.glob(".openfolio-*"))


def test_redaction_rejects_invalid_page_index(make_text_pdf, tmp_path):
    path_in = make_text_pdf("doc.pdf", [(80, 650, "texto")])
    rect = RedactionRect(page_index=3, left=0, bottom=0, right=10, top=10)

    with pytest.raises(ValueError):
        RedactDocument().run(str(path_in), str(tmp_path / "out.pdf"), [rect])


def test_text_hidden_outside_the_cropbox_does_not_survive(make_text_pdf, tmp_path):
    path_in = make_text_pdf(
        "crop.pdf",
        [(80, 650, "visivel"), (80, 100, "ESCONDIDO 123.456.789-09")],
        cropbox=(0, 200, 612, 792),
    )
    path_out = tmp_path / "out.pdf"

    rects = FindSensitiveData().run(str(path_in), kinds=["cpf"])
    assert len(rects) == 1 and rects[0].top < 200  # o pdfium enxerga o texto fora da área visível
    RedactDocument().run(str(path_in), str(path_out), rects)

    page = PdfReader(str(path_out)).pages[0]
    assert page.extract_text().strip() == ""
    # A página nova é só a área visível: o conteúdo escondido fora dela deixou de existir.
    assert (float(page.mediabox.width), float(page.mediabox.height)) == pytest.approx((612, 592))


@pytest.mark.parametrize(
    "phone",
    [
        "(19) 9.8765-4321",  # ponto depois do 9: o formato que escapava (achado num currículo real)
        "(19) 98765-4321",
        "(19)98765-4321",
        "19 98765-4321",
        "19 9 8765-4321",
        "+55 19 98765-4321",
        "+55 (19) 9.8765-4321",
        "(19) 3456-7890",
    ],
)
def test_find_sensitive_data_recognizes_common_phone_formats(tmp_path, phone):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, [f"Telefone / WhatsApp: {phone}"])

    rects = FindSensitiveData().run(str(path_in), kinds=["phone"])

    assert len(rects) == 1
    digits = "".join(ch for ch in phone if ch.isdigit())
    assert "".join(ch for ch in rects[0].text if ch.isdigit()).endswith(digits[-8:])


def test_find_sensitive_data_recognizes_cnpj_without_punctuation(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, ["CNPJ 12345678000190"])

    rects = FindSensitiveData().run(str(path_in), kinds=["cnpj"])

    assert [rect.text for rect in rects] == ["12345678000190"]


def test_find_sensitive_data_reports_kind_and_text_without_duplicates(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, ["CPF: 123.456.789-00"])

    rects = FindSensitiveData().run(
        str(path_in), kinds=["cpf"], custom_pattern=r"\d{3}\.\d{3}\.\d{3}-\d{2}"
    )

    assert len(rects) == 1  # os dois padrões casam no mesmo trecho
    assert rects[0].kind == "cpf"
    assert rects[0].text == "123.456.789-00"


# -- sanitização (B04) ----------------------------------------------------------------------


def _js(code: str) -> DictionaryObject:
    return DictionaryObject(
        {NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject(code)}
    )


def _annotation(writer, subtype: str, **entries):
    annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject(subtype),
            NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (40, 40, 120, 60)]),
        }
    )
    for key, value in entries.items():
        annotation[NameObject(f"/{key}")] = value
    return writer._add_object(annotation)


def _hostile_pdf(path, tmp_path) -> None:
    """PDF com as formas de JavaScript, ações externas e anexos que a sanitização antiga
    deixava passar."""
    source = tmp_path / "_hostile_src.pdf"
    _make_pdf_with_text(source, ["Conteudo visivel do documento"])
    writer = PdfWriter(clone_from=str(source))
    page = writer.pages[0]

    # JavaScript ao abrir a página (/AA da própria página).
    page[NameObject("/AA")] = DictionaryObject({NameObject("/O"): writer._add_object(_js("page_open()"))})

    # Link de URL com JavaScript encadeado em /Next, e link de JavaScript seguido de URL.
    uri_then_js = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject("https://exemplo.com"),
            NameObject("/Next"): _js("chained_after_uri()"),
        }
    )
    js_then_uri = _js("js_before_uri()")
    js_then_uri[NameObject("/Next")] = DictionaryObject(
        {NameObject("/S"): NameObject("/URI"), NameObject("/URI"): TextStringObject("https://seguro.example")}
    )
    launch = DictionaryObject({NameObject("/S"): NameObject("/Launch"), NameObject("/F"): TextStringObject("calc.exe")})
    submit = DictionaryObject(
        {NameObject("/S"): NameObject("/SubmitForm"), NameObject("/F"): TextStringObject("https://coleta.example")}
    )
    js_uri = DictionaryObject(
        {NameObject("/S"): NameObject("/URI"), NameObject("/URI"): TextStringObject("javascript:alert(1)")}
    )

    # Arquivo embutido numa anotação de anexo, com o balão de comentário (Popup) dela.
    embedded = DecodedStreamObject()
    embedded.set_data(b"conteudo secreto do anexo")
    embedded[NameObject("/Type")] = NameObject("/EmbeddedFile")
    filespec = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Filespec"),
            NameObject("/F"): TextStringObject("segredo.txt"),
            NameObject("/EF"): DictionaryObject({NameObject("/F"): writer._add_object(embedded)}),
        }
    )
    attachment = _annotation(writer, "/FileAttachment", FS=filespec)
    popup = _annotation(writer, "/Popup", Parent=attachment)
    attachment.get_object()[NameObject("/Popup")] = popup

    # Campo de formulário com JavaScript no campo-pai (não no widget).
    field_parent = writer._add_object(
        DictionaryObject(
            {
                NameObject("/T"): TextStringObject("cliente"),
                NameObject("/AA"): DictionaryObject({NameObject("/K"): _js("keystroke()")}),
            }
        )
    )
    widget = _annotation(writer, "/Widget", FT=NameObject("/Tx"), T=TextStringObject("nome"), Parent=field_parent)
    field_parent.get_object()[NameObject("/Kids")] = ArrayObject([widget])

    page[NameObject("/Annots")] = ArrayObject(
        [
            _annotation(writer, "/Link", A=uri_then_js),
            _annotation(writer, "/Link", A=js_then_uri),
            _annotation(writer, "/Link", A=launch),
            _annotation(writer, "/Link", A=submit),
            _annotation(writer, "/Link", A=js_uri),
            attachment,
            popup,
            widget,
        ]
    )
    writer.add_js("document_level()")
    writer.add_attachment("anexo_do_documento.txt", b"anexo do documento")
    writer.add_metadata({"/Title": "Titulo secreto"})
    with open(path, "wb") as f:
        writer.write(f)


def test_sanitize_removes_every_hidden_javascript_action_and_attachment(tmp_path):
    path_in = tmp_path / "hostile.pdf"
    _hostile_pdf(path_in, tmp_path)
    path_out = tmp_path / "clean.pdf"

    report = SanitizeDocument().run(str(path_in), str(path_out))

    raw = path_out.read_bytes()
    leftovers = (
        b"page_open", b"chained_after_uri", b"js_before_uri", b"keystroke", b"document_level",
        b"calc.exe", b"coleta.example", b"javascript:", b"conteudo secreto", b"anexo do documento",
    )
    for leftover in leftovers:
        assert leftover not in raw, leftover
    assert find_residual_risks(str(path_out)) == []

    page = PdfReader(str(path_out)).pages[0]
    assert "/AA" not in page
    annotations = [ref.get_object() for ref in page["/Annots"]]
    subtypes = [a["/Subtype"] for a in annotations]
    assert "/FileAttachment" not in subtypes and "/Popup" not in subtypes
    links = [a for a in annotations if a["/Subtype"] == "/Link"]
    # O que era seguro na cadeia de ações continua funcionando.
    targets = sorted(str(link["/A"]["/URI"]) for link in links if "/A" in link)
    assert targets == ["https://exemplo.com", "https://seguro.example"]
    assert all("/Next" not in link["/A"] for link in links if "/A" in link)
    assert "Conteudo visivel do documento" in page.extract_text()

    assert report.javascript >= 6  # página, encadeado, cabeça de cadeia, campo, documento, javascript:
    assert report.external_actions == 2  # Launch e SubmitForm
    assert report.embedded_files == 2  # anotação de anexo + anexo do documento
    assert report.metadata_removed is True


def test_sanitize_does_not_touch_resources_whose_names_look_like_actions(tmp_path):
    # Uma fonte chamada /JS num dicionário de recursos não é JavaScript nem ação:
    # removê-la deixaria a página sem conseguir desenhar o texto.
    source = tmp_path / "_font_src.pdf"
    _make_pdf_with_text(source, ["Texto com fonte de nome estranho"])
    writer = PdfWriter(clone_from=str(source))
    page = writer.pages[0]
    fonts = page["/Resources"]["/Font"]
    (old_name,) = list(fonts.keys())
    fonts[NameObject("/JS")] = fonts.raw_get(old_name)
    del fonts[old_name]
    content = page.get_contents()
    content.set_data(content.get_data().replace(old_name.encode(), b"/JS"))
    page.replace_contents(content)
    path_in = tmp_path / "font_js.pdf"
    with open(path_in, "wb") as f:
        writer.write(f)

    path_out = tmp_path / "out.pdf"
    report = SanitizeDocument().run(str(path_in), str(path_out))

    assert report.javascript == 0
    assert "Texto com fonte de nome estranho" in PdfReader(str(path_out)).pages[0].extract_text()


def test_sanitize_is_not_saved_when_verification_finds_leftovers(tmp_path, monkeypatch):
    path_in = tmp_path / "hostile.pdf"
    _hostile_pdf(path_in, tmp_path)
    path_out = tmp_path / "clean.pdf"
    monkeypatch.setattr(redaction._Sanitizer, "walk", lambda self, roots: None)

    with pytest.raises(SanitizationVerificationError):
        SanitizeDocument().run(str(path_in), str(path_out))

    assert not path_out.exists()


def test_sanitize_keeps_xmp_metadata_only_when_asked(tmp_path):
    source = tmp_path / "_xmp_src.pdf"
    _make_pdf_with_text(source, ["Documento com XMP"])
    writer = PdfWriter(clone_from=str(source))
    xmp = DecodedStreamObject()
    xmp.set_data(b"<x:xmpmeta xmlns:x=\"adobe:ns:meta/\"><dc:title>Titulo XMP</dc:title></x:xmpmeta>")
    xmp[NameObject("/Type")] = NameObject("/Metadata")
    xmp[NameObject("/Subtype")] = NameObject("/XML")
    writer.root_object[NameObject("/Metadata")] = writer._add_object(xmp)
    path_in = tmp_path / "xmp.pdf"
    with open(path_in, "wb") as f:
        writer.write(f)

    kept = tmp_path / "kept.pdf"
    SanitizeDocument().run(str(path_in), str(kept), remove_metadata=False)
    assert b"Titulo XMP" in kept.read_bytes()

    removed = tmp_path / "removed.pdf"
    SanitizeDocument().run(str(path_in), str(removed))
    assert b"Titulo XMP" not in removed.read_bytes()


def test_find_text_ignores_case_and_accents_and_crosses_lines(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(
        path_in,
        ["Contratante: João da Silva", "JOAO DA SILVA assina abaixo, com Maria", "Souza de testemunha"],
    )

    rects = FindSensitiveData().run(str(path_in), search_text="joao da silva; maria souza;")

    assert [(rect.kind, rect.text) for rect in rects] == [
        ("text", "João da Silva"),
        ("text", "JOAO DA SILVA"),
        ("text", "Maria Souza"),
        ("text", "Maria Souza"),
    ]
    # O nome que quebra de linha vira uma caixa em cada linha, só sobre as palavras dele:
    # "Maria" fica no fim da segunda linha, "Souza" no começo da terceira.
    maria, souza = rects[2], rects[3]
    assert maria.top - maria.bottom < 30 and souza.top - souza.bottom < 30
    assert maria.bottom > souza.top - 5
    assert maria.left > souza.right
