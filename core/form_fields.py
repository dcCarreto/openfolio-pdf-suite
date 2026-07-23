"""Criação de campos de formulário (AcroForm) em arquivos PDF.

Os campos são desenhados com o reportlab em um PDF de uma página (o que gera
os widgets AcroForm corretamente), mesclados na página alvo, e registrados no
dicionário /AcroForm do documento para que o campo fique realmente preenchível
em qualquer leitor de PDF.
"""

import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, NameObject
from reportlab.pdfgen import canvas

from .base import PDFOperation

_VALID_FIELD_TYPES = ("text", "checkbox")


class AddFormField(PDFOperation):
    """Adiciona um campo de formulário interativo (texto ou caixa de seleção) a uma página do PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        field_name: str,
        page_number: int,
        x: float,
        y: float,
        width: float = 200,
        height: float = 20,
        field_type: str = "text",
        checked: bool = False,
    ) -> None:
        if field_type not in _VALID_FIELD_TYPES:
            raise ValueError(f"field_type inválido: {field_type}")

        writer = PdfWriter(clone_from=input_path)
        target_page = writer.pages[page_number]
        page_width = float(target_page.mediabox.width)
        page_height = float(target_page.mediabox.height)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
        if field_type == "checkbox":
            c.acroForm.checkbox(name=field_name, x=x, y=y, size=height, checked=checked)
        else:
            c.acroForm.textfield(
                name=field_name, x=x, y=y, width=width, height=height, borderStyle="inset"
            )
        c.showPage()
        c.save()
        buffer.seek(0)

        overlay_reader = PdfReader(buffer)
        overlay_page = overlay_reader.pages[0]
        overlay_acroform = overlay_reader.trailer["/Root"]["/AcroForm"]

        annots_before = list(target_page.get("/Annots", []))
        target_page.merge_page(overlay_page)
        annots_after = list(target_page.get("/Annots", []))
        new_annots = annots_after[len(annots_before) :]

        acroform = writer.root_object.get("/AcroForm")
        if acroform is None:
            acroform = writer._add_object(overlay_acroform.clone(writer))
            acroform_obj = acroform.get_object()
            acroform_obj[NameObject("/Fields")] = ArrayObject(new_annots)
            writer.root_object[NameObject("/AcroForm")] = acroform
        else:
            acroform_obj = acroform.get_object()
            fields = acroform_obj.get("/Fields", ArrayObject())
            for annot in new_annots:
                fields.append(annot)
            acroform_obj[NameObject("/Fields")] = fields

            overlay_fonts = overlay_acroform.get_object().get("/DR", {}).get("/Font", {})
            default_resources = acroform_obj.get("/DR")
            if default_resources is not None and overlay_fonts:
                fonts = default_resources.get_object().get("/Font")
                if fonts is not None:
                    for font_name, font_ref in overlay_fonts.items():
                        if font_name not in fonts:
                            fonts[NameObject(font_name)] = font_ref

        acroform_obj[NameObject("/NeedAppearances")] = BooleanObject(True)

        with open(output_path, "wb") as f:
            writer.write(f)
