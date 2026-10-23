"""Matriz de preservação: o que vive fora das páginas precisa sobreviver às operações.

Antes, quase toda operação copiava só as páginas para um documento novo e descartava
marcadores, metadados, anexos, formulário, rótulos de página, camadas e idioma. Aqui um
documento "completo" passa por cada operação e o resultado é conferido item a item.
"""

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject
from pypdf.xmp import XmpInformation
from reportlab.pdfgen import canvas as rl_canvas

from core import ocr
from core.accessibility import FixBasicAccessibilityIssues
from core.annotations import AddAnnotations, AnnotationSpec
from core.base import add_object
from core.bookmarks import AddBookmarks
from core.compress import CompressPDF
from core.crop import CropPages, ScalePages
from core.edit_text import EditTextArea, TextEditRect
from core.form_fields import AddFormField
from core.links import AddLink
from core.merge import MergePDF
from core.metadata import SetMetadata
from core.page_numbers import AddBatesNumbers, AddHeaderFooter, AddPageNumbers
from core.pages import InsertPages, RemovePages, ReorderPages, ReplacePages, RotatePages
from core.protect import ProtectPDF, UnlockPDF
from core.split import SplitPDF
from core.watermark import AddWatermark

_PAGES = 4
_LABELS = ["i", "ii", "1", "2"]


@pytest.fixture
def rich_pdf(tmp_path):
    source = tmp_path / "_rich_src.pdf"
    canvas = rl_canvas.Canvas(str(source), pagesize=(400, 400))
    for number in range(1, _PAGES + 1):
        canvas.drawString(50, 300, f"Pagina {number} conteudo")
        canvas.showPage()
    canvas.save()

    with_field = tmp_path / "_rich_field.pdf"
    AddFormField().run(str(source), str(with_field), field_name="nome", page_number=0, x=50, y=200)

    writer = PdfWriter(clone_from=str(with_field))
    for index in range(_PAGES):
        writer.add_outline_item(f"Capitulo {index + 1}", index)
    writer.add_metadata({"/Title": "Documento completo", "/Author": "Fulano"})
    xmp = XmpInformation.create()
    xmp.dc_title = {"x-default": "Documento completo"}
    writer.xmp_metadata = xmp
    writer.add_attachment("dados.csv", b"a;b\n1;2\n")
    writer.set_page_label(0, 1, style="/r")
    writer.set_page_label(2, 3, style="/D", start=1)
    writer.root_object[NameObject("/Lang")] = TextStringObject("pt-BR")

    layer = add_object(
        writer,
        DictionaryObject({NameObject("/Type"): NameObject("/OCG"), NameObject("/Name"): TextStringObject("Camada A")})
    )
    writer.root_object[NameObject("/OCProperties")] = DictionaryObject(
        {
            NameObject("/OCGs"): ArrayObject([layer]),
            NameObject("/D"): DictionaryObject({NameObject("/ON"): ArrayObject([layer])}),
        }
    )
    path = tmp_path / "rich.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path


@pytest.fixture
def other_pdf(tmp_path):
    path = tmp_path / "other.pdf"
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 400))
    canvas.drawString(50, 300, "Pagina inserida")
    canvas.showPage()
    canvas.save()
    return path


def _state(path) -> dict:
    reader = PdfReader(str(path))
    root = reader.trailer["/Root"]
    oc = root.get("/OCProperties")
    return {
        "pages": len(reader.pages),
        "outline": [item.title for item in reader.outline if not isinstance(item, list)],
        "title": (reader.metadata or {}).get("/Title"),
        "xmp_title": (reader.xmp_metadata.dc_title or {}).get("x-default") if reader.xmp_metadata else None,
        "attachments": sorted(reader.attachments),
        "fields": sorted(reader.get_fields() or {}),
        "labels": list(reader.page_labels) if "/PageLabels" in root else None,
        "layers": len(oc.get_object()["/OCGs"]) if oc is not None else 0,
        "lang": root.get("/Lang"),
    }


def _fake_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(
        ocr,
        "_run_tesseract",
        lambda image, language: {"text": ["OCR"], "left": [10], "top": [10], "width": [40], "height": [20], "conf": [95]},
    )


_IN_PLACE = {
    "marca d'agua": lambda i, o: AddWatermark().run(i, o, text="CONFIDENCIAL"),
    "comprimir": lambda i, o: CompressPDF().run(i, o),
    "rotacionar": lambda i, o: RotatePages().run(i, o, 90, [1]),
    "cortar": lambda i, o: CropPages().run(i, o, 5, 5, 5, 5),
    "redimensionar": lambda i, o: ScalePages().run(i, o, 595, 842),
    "numeracao": lambda i, o: AddPageNumbers().run(i, o),
    "bates": lambda i, o: AddBatesNumbers().run(i, o, prefix="X-"),
    "cabecalho": lambda i, o: AddHeaderFooter().run(i, o, text="Pagina {page} de {pages}"),
    "marcadores": lambda i, o: AddBookmarks().run(i, o, [("Extra", 3)]),
    "anotacoes": lambda i, o: AddAnnotations().run(i, o, [AnnotationSpec(0, "note", position=(10, 10), text="n")]),
    "link": lambda i, o: AddLink().run(i, o, 0, 10, 10, 50, 30, url="https://exemplo.com"),
    "editar texto": lambda i, o: EditTextArea().run(i, o, [TextEditRect(1, 40, 290, 200, 320, "novo")]),
    "ocr": lambda i, o: ocr.OCRDocument().run(i, o, skip_pages_with_text=False),
}


@pytest.mark.parametrize("name", list(_IN_PLACE))
def test_in_place_operations_keep_everything(rich_pdf, tmp_path, monkeypatch, name):
    _fake_tesseract(monkeypatch)
    before = _state(rich_pdf)
    output = tmp_path / "out.pdf"

    _IN_PLACE[name](str(rich_pdf), str(output))

    after = _state(output)
    for key in ("pages", "title", "xmp_title", "attachments", "fields", "labels", "layers", "lang"):
        assert after[key] == before[key], key
    assert after["outline"][: len(before["outline"])] == before["outline"]


def test_metadata_updates_info_and_xmp_and_keeps_the_rest(rich_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    SetMetadata().run(str(rich_pdf), str(output), title="Titulo novo")

    after = _state(output)
    assert after["title"] == "Titulo novo"
    assert after["xmp_title"] == "Titulo novo"  # leitores que preferem o XMP veem o mesmo título
    assert after["outline"] == _state(rich_pdf)["outline"]
    assert after["attachments"] == ["dados.csv"]


def test_accessibility_fix_keeps_the_rest(rich_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    FixBasicAccessibilityIssues().run(str(rich_pdf), str(output), language="en", title="Doc")

    after = _state(output)
    assert after["lang"] == "en"
    assert after["outline"] == _state(rich_pdf)["outline"]
    assert after["fields"] == ["nome"]


def test_protect_then_unlock_round_trip_keeps_everything(rich_pdf, tmp_path):
    protected = tmp_path / "protected.pdf"
    unlocked = tmp_path / "unlocked.pdf"
    ProtectPDF().run(str(rich_pdf), str(protected), password="segredo")
    UnlockPDF().run(str(protected), str(unlocked), password="segredo")

    before, after = _state(rich_pdf), _state(unlocked)
    for key in ("outline", "title", "attachments", "fields", "labels", "layers", "lang"):
        assert after[key] == before[key], key


def test_remove_pages_keeps_structure_of_the_remaining_pages(rich_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    RemovePages().run(str(rich_pdf), str(output), pages=[2])

    after = _state(output)
    assert after["pages"] == 3
    assert after["outline"] == ["Capitulo 1", "Capitulo 2", "Capitulo 4"]
    assert after["labels"] == ["i", "ii", "2"]  # cada página mantém o rótulo que tinha
    assert after["title"] == "Documento completo"
    assert after["xmp_title"] == "Documento completo"
    assert after["attachments"] == ["dados.csv"]
    assert after["fields"] == ["nome"]
    assert after["layers"] == 1
    assert after["lang"] == "pt-BR"
    # O conteúdo da página removida não pode continuar dentro do arquivo.
    assert b"Pagina 3 conteudo" not in output.read_bytes()


def test_removing_the_page_with_the_form_field_removes_the_field(rich_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    RemovePages().run(str(rich_pdf), str(output), pages=[0])

    assert _state(output)["fields"] == []


def test_reorder_keeps_everything_following_the_pages(rich_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    ReorderPages().run(str(rich_pdf), str(output), order=[3, 2, 1, 0])

    after = _state(output)
    assert after["labels"] == ["2", "1", "ii", "i"]
    assert sorted(after["outline"]) == sorted(_state(rich_pdf)["outline"])
    reader = PdfReader(str(output))
    assert "Pagina 4" in reader.pages[0].extract_text()
    assert reader.get_destination_page_number(reader.outline[0]) in range(4)
    assert after["fields"] == ["nome"]
    assert after["attachments"] == ["dados.csv"]


def test_insert_and_replace_keep_the_main_document_properties(rich_pdf, other_pdf, tmp_path):
    inserted = tmp_path / "inserted.pdf"
    InsertPages().run(str(rich_pdf), str(inserted), str(other_pdf), at_index=0)
    after = _state(inserted)
    assert after["pages"] == 5
    assert after["title"] == "Documento completo"  # mesmo com a página nova no início
    assert after["labels"][1:] == _LABELS
    assert after["attachments"] == ["dados.csv"]

    replaced = tmp_path / "replaced.pdf"
    ReplacePages().run(str(rich_pdf), str(replaced), str(other_pdf), start_index=1, end_index=3)
    after = _state(replaced)
    assert after["pages"] == 3
    assert after["outline"] == ["Capitulo 1", "Capitulo 4"]
    assert after["fields"] == ["nome"]
    assert b"Pagina 2 conteudo" not in replaced.read_bytes()


def test_merge_keeps_metadata_attachments_and_layers(rich_pdf, other_pdf, tmp_path):
    output = tmp_path / "merged.pdf"
    MergePDF().run([str(rich_pdf), str(other_pdf)], str(output))

    after = _state(output)
    assert after["pages"] == 5
    assert after["title"] == "Documento completo"
    assert after["attachments"] == ["dados.csv"]
    assert after["layers"] == 1
    assert after["labels"][:4] == _LABELS
    assert after["fields"] == ["nome"]


def test_split_parts_keep_their_labels_and_metadata(rich_pdf, tmp_path):
    parts = SplitPDF().run(str(rich_pdf), str(tmp_path / "partes"), pages_per_file=2)

    first, second = (_state(part) for part in parts)
    assert first["labels"] == ["i", "ii"] and second["labels"] == ["1", "2"]
    assert first["title"] == second["title"] == "Documento completo"
    assert first["outline"] == ["Capitulo 1", "Capitulo 2"]
    assert second["outline"] == ["Capitulo 3", "Capitulo 4"]
    assert first["fields"] == ["nome"] and second["fields"] == []
