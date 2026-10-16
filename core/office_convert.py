"""Conversão de documentos do Office (Word, Excel, PowerPoint) para PDF.

Usa o LibreOffice (se estiver instalado na máquina) para uma conversão fiel ao arquivo
original; com ele, também aceita os formatos antigos e os do próprio LibreOffice (.doc,
.xls, .ppt, .odt, .ods, .odp, .rtf).

Sem o LibreOffice, cai para uma conversão básica em Python puro (python-docx, openpyxl e
python-pptx + reportlab) dos formatos .docx, .xlsx e .pptx. Ela leva o texto, os títulos,
as listas e as tabelas, mas não a formatação visual exata, e descarta imagens, gráficos,
cabeçalhos e rodapés. O que foi descartado volta como aviso no resultado
(`OfficeConversionResult.warnings`), para a interface mostrar — antes o conteúdo sumia sem
aviso (tabelas do Word inteiras, e o texto que não cabia num slide).
"""

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .base import PDFOperation, atomic_output
from .external import find_program, run_cancellable
from .fonts import SANS, SANS_BOLD, register_fonts
from .messages import Message
from .progress import Progress, ensure_progress

_LIBREOFFICE_TIMEOUT = 120  # segundos

_LIBREOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]

BASIC_SUFFIXES = (".docx", ".xlsx", ".pptx")
LIBREOFFICE_ONLY_SUFFIXES = (".doc", ".xls", ".ppt", ".odt", ".ods", ".odp", ".rtf")
SUPPORTED_SUFFIXES = BASIC_SUFFIXES + LIBREOFFICE_ONLY_SUFFIXES

_MAX_SHEET_COLUMNS = 40  # acima disso as colunas ficariam ilegíveis numa página


def find_libreoffice() -> str | None:
    """Procura o executável do LibreOffice no PATH e em locais comuns de instalação."""
    return find_program(_LIBREOFFICE_CANDIDATES)


@dataclass
class OfficeConversionResult:
    used_libreoffice: bool
    warnings: list[str] = field(default_factory=list)


class ConvertOfficeToPDF(PDFOperation):
    """Converte um documento do Office (ou do LibreOffice) para PDF."""

    def run(self, input_path: str, output_path: str, progress: Progress | None = None) -> OfficeConversionResult:
        progress = ensure_progress(progress)
        suffix = Path(input_path).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise ValueError(Message("Formato não suportado: {suffix}", suffix=suffix))

        libreoffice_path = find_libreoffice()
        if not libreoffice_path and suffix in LIBREOFFICE_ONLY_SUFFIXES:
            raise ValueError(
                Message(
                    "Arquivos {suffix} só podem ser convertidos com o LibreOffice instalado "
                    "(libreoffice.org). Sem ele, salve o arquivo como .docx, .xlsx ou .pptx.",
                    suffix=suffix,
                )
            )

        with atomic_output(output_path) as temp_path:
            progress.update(0, 0, "Convertendo o documento")
            if libreoffice_path:
                self._convert_with_libreoffice(libreoffice_path, input_path, temp_path, progress)
                result = OfficeConversionResult(used_libreoffice=True)
            else:
                warnings = self._convert_with_fallback(input_path, temp_path, suffix)
                result = OfficeConversionResult(used_libreoffice=False, warnings=warnings)
            progress.check()
        return result

    def _convert_with_libreoffice(
        self, libreoffice_path: str, input_path: str, output_path: str, progress: Progress
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Perfil de usuário isolado por conversão: sem isso, chamadas concorrentes/
            # rápidas ao soffice competem pelo lock do perfil padrão e podem travar até
            # o timeout em vez de converter.
            profile_dir = Path(tmp_dir) / "profile"
            returncode, stderr = run_cancellable(
                [
                    libreoffice_path,
                    "--headless",
                    f"-env:UserInstallation={profile_dir.as_uri()}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmp_dir,
                    input_path,
                ],
                progress,
                timeout=_LIBREOFFICE_TIMEOUT,
                program="O LibreOffice",
            )
            if returncode != 0:
                detail = stderr.decode(errors="replace").strip() or f"código de saída {returncode}"
                raise RuntimeError(Message("O LibreOffice falhou ao converter o arquivo: {detail}", detail=detail))

            generated_path = Path(tmp_dir) / f"{Path(input_path).stem}.pdf"
            if not generated_path.is_file():
                raise RuntimeError("O LibreOffice não gerou o arquivo PDF esperado.")
            shutil.copy(generated_path, output_path)

    def _convert_with_fallback(self, input_path: str, output_path: str, suffix: str) -> list[str]:
        register_fonts()
        if suffix == ".docx":
            return _docx_to_pdf(input_path, output_path)
        if suffix == ".xlsx":
            return _xlsx_to_pdf(input_path, output_path)
        return _pptx_to_pdf(input_path, output_path)


def _styles():
    """Estilos do reportlab com a fonte embutida (acentos e símbolos fora do Latin-1)."""
    sheet = getSampleStyleSheet()
    styles = {}
    for name in ("Normal", "Title", "Heading1", "Heading2", "Heading3", "Heading4"):
        base = sheet[name]
        styles[name] = ParagraphStyle(
            f"OpenFolio{name}", parent=base, fontName=SANS if name == "Normal" else SANS_BOLD
        )
    styles["Bullet"] = ParagraphStyle("OpenFolioBullet", parent=styles["Normal"], leftIndent=14, bulletIndent=4)
    styles["Cell"] = ParagraphStyle("OpenFolioCell", parent=styles["Normal"], fontSize=8, leading=10)
    return styles


def _paragraph(text: str, style) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _table(rows: list[list[str]], available_width: float, cell_style) -> Table:
    columns = max(len(row) for row in rows)
    padded = [row + [""] * (columns - len(row)) for row in rows]
    data = [[_paragraph(text, cell_style) for text in row] for row in padded]
    table = Table(data, colWidths=[available_width / columns] * columns, repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


# --- Word ------------------------------------------------------------------------------


def _docx_to_pdf(input_path: str, output_path: str) -> list[str]:
    from docx import Document
    from docx.table import Table as DocxTable

    document = Document(input_path)
    styles = _styles()
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    story = []

    for block in document.iter_inner_content():
        if isinstance(block, DocxTable):
            rows = _docx_table_rows(block)
            if rows:
                story.append(_table(rows, doc.width, styles["Cell"]))
                story.append(Spacer(1, 8))
            continue
        text = block.text.strip()
        if not text:
            story.append(Spacer(1, 10))
            continue
        style_name = (block.style.name if block.style is not None else "") or ""
        if style_name == "Title":
            story.append(_paragraph(text, styles["Title"]))
        elif style_name.startswith(("Heading", "Título")):
            level = "".join(ch for ch in style_name if ch.isdigit()) or "2"
            story.append(_paragraph(text, styles.get(f"Heading{min(int(level), 4)}", styles["Heading2"])))
        elif _is_list_item(block):
            story.append(Paragraph(escape(text), styles["Bullet"], bulletText="•"))
        else:
            story.append(_paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 4))

    if not story:
        story.append(_paragraph("(documento vazio)", styles["Normal"]))
    doc.build(story)

    warnings = []
    if document.inline_shapes or _docx_has_floating_images(document):
        warnings.append(Message("As imagens do documento não foram incluídas."))
    if any(_section_has_text(section) for section in document.sections):
        warnings.append(Message("Cabeçalhos e rodapés não foram incluídos."))
    return warnings


def _docx_table_rows(table) -> list[list[str]]:
    rows = []
    for row in table.rows:
        seen = set()
        cells = []
        for cell in row.cells:
            # Células mescladas aparecem repetidas em `row.cells`: o texto vai só na primeira.
            key = id(cell._tc)
            cells.append("" if key in seen else cell.text.strip())
            seen.add(key)
        rows.append(cells)
    return [row for row in rows if any(row)]


def _is_list_item(paragraph) -> bool:
    properties = paragraph._p.pPr
    if properties is not None and properties.numPr is not None:
        return True
    style_name = (paragraph.style.name if paragraph.style is not None else "") or ""
    return style_name.startswith("List")


def _docx_has_floating_images(document) -> bool:
    return bool(document.element.body.xpath(".//*[local-name()='anchor']"))


def _section_has_text(section) -> bool:
    for part in (section.header, section.footer):
        try:
            if not part.is_linked_to_previous and any(p.text.strip() for p in part.paragraphs):
                return True
        except Exception:
            continue
    return False


# --- Excel -----------------------------------------------------------------------------


def _xlsx_to_pdf(input_path: str, output_path: str) -> list[str]:
    from openpyxl import load_workbook

    workbook = load_workbook(input_path, data_only=True)
    styles = _styles()
    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4))
    story = []
    warnings = []

    for sheet in workbook.worksheets:
        story.append(_paragraph(sheet.title, styles["Heading2"]))
        rows = [["" if cell is None else str(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
        rows = _trim_empty(rows)
        if rows:
            if len(rows[0]) > _MAX_SHEET_COLUMNS:
                warnings.append(
                    Message(
                        'A planilha "{sheet}" tem {columns} colunas; só as {limit} primeiras foram incluídas.',
                        sheet=sheet.title,
                        columns=len(rows[0]),
                        limit=_MAX_SHEET_COLUMNS,
                    )
                )
                rows = [row[:_MAX_SHEET_COLUMNS] for row in rows]
            story.append(_table(rows, doc.width, styles["Cell"]))
        if getattr(sheet, "_charts", None) or getattr(sheet, "_images", None):
            warnings.append(
                Message('Gráficos e imagens da planilha "{sheet}" não foram incluídos.', sheet=sheet.title)
            )
        story.append(Spacer(1, 20))

    if not story:
        story.append(_paragraph("(planilha vazia)", styles["Normal"]))
    doc.build(story)
    return warnings


def _trim_empty(rows: list[list[str]]) -> list[list[str]]:
    """Tira as linhas e colunas vazias do fim (o openpyxl lê até a última célula formatada)."""
    while rows and not any(rows[-1]):
        rows.pop()
    if not rows:
        return rows
    last_column = max((max((i for i, value in enumerate(row) if value), default=-1) for row in rows), default=-1)
    return [row[: last_column + 1] for row in rows]


# --- PowerPoint ------------------------------------------------------------------------


def _pptx_to_pdf(input_path: str, output_path: str) -> list[str]:
    """Um slide por página; quando o texto não cabe, o slide continua na página seguinte
    (antes o excesso era cortado sem aviso)."""
    from pptx import Presentation

    presentation = Presentation(input_path)
    styles = _styles()
    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4))
    story = []
    images = 0
    continued = 0

    for number, slide in enumerate(presentation.slides, start=1):
        if number > 1:
            story.append(PageBreak())
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None and slide.shapes.title.has_text_frame else ""
        story.append(_paragraph(title or f"Slide {number}", styles["Heading1"]))
        blocks, slide_images = _slide_blocks(slide.shapes, skip=slide.shapes.title)
        images += slide_images
        slide_story = []
        for kind, value in blocks:
            if kind == "table":
                slide_story.append(_table(value, doc.width, styles["Cell"]))
                slide_story.append(Spacer(1, 6))
            else:
                text, level = value
                style = ParagraphStyle(
                    f"OpenFolioSlide{level}", parent=styles["Bullet"], leftIndent=14 + 16 * level, bulletIndent=4 + 16 * level
                )
                slide_story.append(Paragraph(escape(text), style, bulletText="•"))
        if _story_height(slide_story, doc.width) > doc.height - 60:
            continued += 1
        story.extend(slide_story)

    if not story:
        story.append(_paragraph("(apresentação vazia)", styles["Normal"]))
    doc.build(story)

    warnings = []
    if continued:
        warnings.append(
            Message("{count} slide(s) com texto demais para uma página continuaram na página seguinte.", count=continued)
        )
    if images:
        warnings.append(Message("As imagens e gráficos dos slides não foram incluídos."))
    return warnings


def _slide_blocks(shapes, skip=None) -> tuple[list, int]:
    """Texto (com o nível de recuo) e tabelas das formas de um slide, na ordem, entrando em
    grupos. Devolve também quantas imagens/gráficos ficaram de fora."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    blocks, images = [], 0
    for shape in shapes:
        if skip is not None and shape.shape_id == skip.shape_id:
            continue
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            inner, inner_images = _slide_blocks(shape.shapes)
            blocks.extend(inner)
            images += inner_images
        elif getattr(shape, "has_table", False) and shape.has_table:
            rows = [[cell.text.strip() for cell in row.cells] for row in shape.table.rows]
            if any(any(row) for row in rows):
                blocks.append(("table", rows))
        elif shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                text = "".join(run.text for run in paragraph.runs).strip()
                if text:
                    blocks.append(("text", (text, min(paragraph.level, 4))))
        elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE or getattr(shape, "has_chart", False):
            images += 1
    return blocks, images


def _story_height(flowables, width: float) -> float:
    return sum(flowable.wrap(width, 10_000)[1] for flowable in flowables)
