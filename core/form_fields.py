"""Criação de campos de formulário (AcroForm) em arquivos PDF.

Os campos são desenhados com o reportlab em um PDF de uma página (o que gera
os widgets AcroForm corretamente), mesclados na página alvo, e registrados no
dicionário /AcroForm do documento para que o campo fique realmente preenchível
em qualquer leitor de PDF.
"""

import csv
import io
import re
from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, NameObject
from reportlab.pdfgen import canvas

from .base import PDFOperation, open_reader, require_valid_page_index

_VALID_FIELD_TYPES = ("text", "checkbox", "date", "dropdown", "listbox")
_CHOICE_FIELD_TYPES = ("dropdown", "listbox")


class AddFormField(PDFOperation):
    """Adiciona um campo de formulário interativo (texto, data, caixa de seleção, lista
    suspensa ou lista de seleção) a uma página do PDF. Campo de data é um campo de texto
    comum com uma dica de formato no tooltip — PDF não tem um tipo de campo "data" nativo,
    e validar o formato exigiria uma ação de JavaScript, que este projeto evita adicionar
    de propósito (o mesmo motivo por trás de `core/pdfa.py` e `core/redaction.py` removerem
    JavaScript de PDFs de entrada)."""

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
        options: list[str] | None = None,
    ) -> None:
        if field_type not in _VALID_FIELD_TYPES:
            raise ValueError(f"field_type inválido: {field_type}")
        if field_type in _CHOICE_FIELD_TYPES and not options:
            raise ValueError(f"Informe ao menos uma opção (options) para o tipo {field_type}.")

        reader = open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        require_valid_page_index(len(reader.pages), page_number)

        writer = PdfWriter(clone_from=input_path)
        target_page = writer.pages[page_number]
        page_width = float(target_page.mediabox.width)
        page_height = float(target_page.mediabox.height)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
        if field_type == "checkbox":
            c.acroForm.checkbox(name=field_name, x=x, y=y, size=height, checked=checked)
        elif field_type == "dropdown":
            # reportlab tem um bug conhecido (confirmado nesta sessão): choice()/listbox()
            # sem um `value` não-vazio deixam uma variável local (`lbextras`) sem atribuir
            # e derrubam com UnboundLocalError antes mesmo de desenhar o campo. Pré-selecionar
            # a primeira opção evita esse caminho de código, sem mudar o que o usuário vê
            # como padrão razoável (a maioria dos leitores já mostra a primeira opção).
            c.acroForm.choice(
                name=field_name,
                x=x,
                y=y,
                width=width,
                height=height,
                options=list(options),
                value=str(options[0]),
            )
        elif field_type == "listbox":
            c.acroForm.listbox(
                name=field_name,
                x=x,
                y=y,
                width=width,
                height=height,
                options=list(options),
                value=str(options[0]),
            )
        else:
            tooltip = "Data (DD/MM/AAAA)" if field_type == "date" else None
            c.acroForm.textfield(
                name=field_name,
                x=x,
                y=y,
                width=width,
                height=height,
                borderStyle="inset",
                tooltip=tooltip,
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
        # Comparação por identidade (não por posição): merge_page normalmente só anexa
        # ao final de /Annots, mas depender dessa ordem seria uma suposição implícita
        # sobre o comportamento interno do pypdf.
        new_annots = [annot for annot in annots_after if annot not in annots_before]

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


@dataclass
class RadioOption:
    """Uma opção de um grupo de botões de opção (radio): valor exportado e posição."""

    value: str
    page_number: int
    x: float
    y: float


class AddRadioGroup(PDFOperation):
    """Adiciona um grupo de botões de opção (radio) — várias opções mutuamente exclusivas
    compartilhando um único campo, cada uma podendo estar numa página diferente (comum em
    formulários longos com "assinale uma opção" repetido em várias páginas).

    Diferente de um campo de texto/caixa de seleção (onde o widget na página *é* o campo),
    um grupo radio no PDF é um campo-pai (`/FT /Btn`) sem posição própria, com um widget
    filho (`/Kids`) por opção. O reportlab já monta essa estrutura corretamente ao desenhar
    todas as opções num único `Canvas` com o mesmo `name` — o que exigiu confirmação
    empírica nesta sessão foi que juntar os widgets de páginas diferentes de volta ao
    documento original via `merge_page` (a mesma técnica de `AddFormField`) preserva o
    vínculo `/Parent`/`/Kids` só se ele for reconstruído à mão depois do merge: o pypdf
    clona cada widget isoladamente por chamada de `merge_page`, então o campo-pai
    compartilhado precisa ser criado uma única vez aqui e referenciado por todos os widgets
    já clonados, em vez de confiar em `merge_page` para propagar essa relação sozinho.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        field_name: str,
        options: list[RadioOption],
        size: float = 16,
        selected_value: str | None = None,
    ) -> None:
        if len(options) < 2:
            raise ValueError("Um grupo de opções precisa de pelo menos duas opções.")
        values = [opt.value for opt in options]
        if len(set(values)) != len(values):
            raise ValueError("Os valores das opções devem ser únicos.")
        if selected_value is not None and selected_value not in values:
            raise ValueError("selected_value deve ser um dos valores das opções.")

        reader = open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        for opt in options:
            require_valid_page_index(len(reader.pages), opt.page_number, label="Página em options")

        writer = PdfWriter(clone_from=input_path)

        options_by_page: dict[int, list[RadioOption]] = {}
        for opt in options:
            options_by_page.setdefault(opt.page_number, []).append(opt)
        max_page = max(options_by_page)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer)
        for page_index in range(max_page + 1):
            page_width = float(writer.pages[page_index].mediabox.width)
            page_height = float(writer.pages[page_index].mediabox.height)
            c.setPageSize((page_width, page_height))
            for opt in options_by_page.get(page_index, []):
                c.acroForm.radio(
                    name=field_name,
                    value=opt.value,
                    selected=(opt.value == selected_value),
                    x=opt.x,
                    y=opt.y,
                    size=size,
                )
            c.showPage()
        c.save()
        buffer.seek(0)

        overlay_reader = PdfReader(buffer)
        overlay_parent = overlay_reader.trailer["/Root"]["/AcroForm"]["/Fields"][0].get_object()
        overlay_acroform = overlay_reader.trailer["/Root"]["/AcroForm"]

        kid_refs = []
        for page_index, page_options in options_by_page.items():
            target_page = writer.pages[page_index]
            annots_before = list(target_page.get("/Annots", []))
            target_page.merge_page(overlay_reader.pages[page_index])
            annots_after = list(target_page.get("/Annots", []))
            kid_refs.extend(annot for annot in annots_after if annot not in annots_before)

        parent = DictionaryObject()
        parent[NameObject("/FT")] = NameObject("/Btn")
        parent[NameObject("/Ff")] = overlay_parent.raw_get("/Ff")
        parent[NameObject("/T")] = overlay_parent.raw_get("/T")
        if "/V" in overlay_parent:
            parent[NameObject("/V")] = overlay_parent.raw_get("/V")
        parent[NameObject("/Kids")] = ArrayObject(kid_refs)
        parent_ref = writer._add_object(parent)
        for kid_ref in kid_refs:
            kid_ref.get_object()[NameObject("/Parent")] = parent_ref

        acroform = writer.root_object.get("/AcroForm")
        if acroform is None:
            acroform = writer._add_object(overlay_acroform.clone(writer))
            acroform_obj = acroform.get_object()
            acroform_obj[NameObject("/Fields")] = ArrayObject([parent_ref])
            writer.root_object[NameObject("/AcroForm")] = acroform
        else:
            acroform_obj = acroform.get_object()
            fields = acroform_obj.get("/Fields", ArrayObject())
            fields.append(parent_ref)
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


@dataclass
class FormFieldInfo:
    """Descrição resumida de um campo de formulário já existente num PDF."""

    name: str
    field_type: str
    value: str


# Bits de /Ff (ISO 32000-1, tabela 221/226/227) que distinguem subtipos de /Btn e /Ch.
_FLAG_RADIO = 1 << 15
_FLAG_PUSHBUTTON = 1 << 16
_FLAG_COMBO = 1 << 17


def _describe_field_type(field) -> str:
    field_type = field.field_type
    flags = int(field.flags or 0)
    if field_type == "/Tx":
        return "text"
    if field_type == "/Btn":
        if flags & _FLAG_RADIO:
            return "radio"
        if flags & _FLAG_PUSHBUTTON:
            return "button"
        return "checkbox"
    if field_type == "/Ch":
        return "dropdown" if flags & _FLAG_COMBO else "listbox"
    if field_type == "/Sig":
        return "signature"
    return "unknown"


class ListFormFields(PDFOperation):
    """Lista os campos de formulário já existentes num PDF: nome, tipo e valor atual."""

    def run(self, input_path: str) -> list[FormFieldInfo]:
        reader = open_reader(input_path)
        fields = reader.get_fields() or {}
        return [
            FormFieldInfo(
                name=name,
                field_type=_describe_field_type(field),
                value="" if field.value is None else str(field.value),
            )
            for name, field in fields.items()
        ]


class ExportFormDataCSV(PDFOperation):
    """Exporta nome, tipo e valor atual de cada campo de um PDF para um arquivo CSV."""

    def run(self, input_path: str, output_path: str) -> int:
        fields = ListFormFields().run(input_path)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            csv_writer = csv.writer(f)
            csv_writer.writerow(["campo", "tipo", "valor"])
            for field in fields:
                csv_writer.writerow([field.name, field.field_type, field.value])
        return len(fields)


class ImportFormDataCSV(PDFOperation):
    """Preenche os campos de um PDF a partir de um CSV com colunas "campo" e "valor"
    (aceita também "name"/"value", para CSVs exportados de outras ferramentas). Caixas de
    seleção e listas recebem o valor bruto do PDF (ex.: "/Yes", "/Off", o nome de uma
    opção) — não um rótulo amigável — porque é esse o mesmo formato que `ExportFormDataCSV`
    grava, então uma volta completa exportar → editar → importar sempre é consistente."""

    def run(self, input_path: str, output_path: str, csv_path: str) -> int:
        open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        writer = PdfWriter(clone_from=input_path)

        values: dict[str, str] = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("campo") or row.get("name")
                if not name:
                    continue
                values[name] = row.get("valor") or row.get("value") or ""

        if not values:
            raise ValueError("Nenhum campo com nome válido encontrado no CSV.")

        writer.update_page_form_field_values(list(writer.pages), values, auto_regenerate=False)
        with open(output_path, "wb") as f:
            writer.write(f)
        return len(values)


def _fdf_hex_string(value: str) -> str:
    # Hexadecimal com BOM UTF-16BE (em vez de string literal com parênteses) evita ter que
    # escapar "\", "(" e ")" na mão — a fonte mais comum de FDF malformado feito à unha — e
    # já suporta acentos/Unicode sem depender de PDFDocEncoding.
    return "<FEFF" + value.encode("utf-16-be").hex().upper() + ">"


class ExportFormDataFDF(PDFOperation):
    """Exporta os valores atuais dos campos de um PDF para um arquivo FDF (o formato nativo
    do Acrobat para dados de formulário) — útil para reaproveitar os mesmos dados em outra
    cópia do mesmo formulário."""

    def run(self, input_path: str, output_path: str) -> int:
        fields = ListFormFields().run(input_path)
        lines = ["%FDF-1.2", "1 0 obj", "<<", "/FDF", "<<", "/Fields ["]
        for field in fields:
            lines.append("<<")
            lines.append(f"/T {_fdf_hex_string(field.name)}")
            lines.append(f"/V {_fdf_hex_string(field.value)}")
            lines.append(">>")
        lines.extend(["]", ">>", ">>", "endobj", "trailer", "<<", "/Root 1 0 R", ">>", "%%EOF"])
        with open(output_path, "wb") as f:
            f.write("\n".join(lines).encode("ascii"))
        return len(fields)


_FDF_ENTRY_RE = re.compile(
    r"/T\s*(?:\((?P<t_lit>(?:\\.|[^()])*)\)|<(?P<t_hex>[0-9A-Fa-f\s]*)>)\s*"
    r"/V\s*(?:\((?P<v_lit>(?:\\.|[^()])*)\)|<(?P<v_hex>[0-9A-Fa-f\s]*)>)",
    re.DOTALL,
)


def _decode_fdf_hex(hex_text: str) -> str:
    raw = bytes.fromhex(re.sub(r"\s+", "", hex_text))
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be")
    return raw.decode("latin-1")


def _decode_fdf_literal(text: str) -> str:
    return text.replace(r"\)", ")").replace(r"\(", "(").replace(r"\\", "\\")


class ImportFormDataFDF(PDFOperation):
    """Importa valores de campos a partir de um arquivo FDF e preenche o PDF.

    Suporta o subconjunto de FDF mais comum: uma lista plana de entradas `/T`/`/V` por
    campo, com valor em string literal ou hexadecimal (o formato usado por
    `ExportFormDataFDF` e pelo Acrobat para texto Unicode). Não suporta nomes de campo
    hierárquicos (`/Kids` dentro do próprio FDF) nem múltiplos valores por campo — para
    isso, o formato CSV é mais direto de qualquer forma.
    """

    def run(self, input_path: str, output_path: str, fdf_path: str) -> int:
        open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        writer = PdfWriter(clone_from=input_path)

        with open(fdf_path, "rb") as f:
            text = f.read().decode("latin-1")

        values: dict[str, str] = {}
        for match in _FDF_ENTRY_RE.finditer(text):
            name = (
                _decode_fdf_hex(match["t_hex"])
                if match["t_hex"] is not None
                else _decode_fdf_literal(match["t_lit"])
            )
            value = (
                _decode_fdf_hex(match["v_hex"])
                if match["v_hex"] is not None
                else _decode_fdf_literal(match["v_lit"])
            )
            values[name] = value

        if not values:
            raise ValueError("Nenhum campo encontrado no arquivo FDF.")

        writer.update_page_form_field_values(list(writer.pages), values, auto_regenerate=False)
        with open(output_path, "wb") as f:
            writer.write(f)
        return len(values)


def _remove_flattened_fields(writer: PdfWriter, field_names: set[str]) -> None:
    """Remove do documento os widgets de campos já achatados.

    `PdfWriter.update_page_form_field_values(..., flatten=True)` só cola a aparência do
    campo no conteúdo da página — a própria docstring do pypdf avisa que "this option does
    not remove the annotation itself" — então sem este passo o campo continuaria interativo
    por cima do texto já desenhado (duplicado visualmente e ainda editável). Como todo campo
    criado por `AddFormField`/`AddRadioGroup` neste projeto é sempre de nível raiz (nunca
    aninhado sob outro campo pai), remover pelo `/T` do topo de `/AcroForm/Fields` — e os
    widgets correspondentes (o próprio campo, ou seus `/Kids` num grupo radio) de `/Annots`
    — é suficiente; não precisa da generalidade de nomes de campo hierárquicos.
    """
    acroform = writer.root_object.get("/AcroForm")
    if acroform is None:
        return
    acroform_obj = acroform.get_object()
    top_fields = acroform_obj.get("/Fields")
    if not top_fields:
        return

    remaining_fields = ArrayObject()
    removed_widget_ids: set[int] = set()
    for field_ref in top_fields:
        field_obj = field_ref.get_object()
        if field_obj.get("/T") in field_names:
            widgets = field_obj.get("/Kids") or [field_ref]
            removed_widget_ids.update(id(widget_ref.get_object()) for widget_ref in widgets)
        else:
            remaining_fields.append(field_ref)
    acroform_obj[NameObject("/Fields")] = remaining_fields

    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        kept = ArrayObject(a for a in annots if id(a.get_object()) not in removed_widget_ids)
        if len(kept) != len(annots):
            page[NameObject("/Annots")] = kept


class FlattenFormFields(PDFOperation):
    """Achata os campos de formulário de um PDF: grava o valor atual de cada campo
    preenchido como conteúdo estático da página e remove o widget interativo — um "Fill &
    Sign" simplificado, para garantir que os valores não sejam alterados depois de
    preenchidos. Campos sem valor definido são deixados como estão (não há o que achatar
    num campo em branco)."""

    def run(self, input_path: str, output_path: str) -> int:
        open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        writer = PdfWriter(clone_from=input_path)

        fields = writer.get_fields() or {}
        values = {name: field.value for name, field in fields.items() if field.value is not None}
        if values:
            writer.update_page_form_field_values(
                list(writer.pages), values, auto_regenerate=False, flatten=True
            )
            _remove_flattened_fields(writer, set(values.keys()))

        with open(output_path, "wb") as f:
            writer.write(f)
        return len(values)
