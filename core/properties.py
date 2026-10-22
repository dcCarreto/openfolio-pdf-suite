"""Propriedades do documento (A12): versão, tamanho, produtor, proteção e permissões,
fontes usadas (e se estão embutidas) e tamanhos de página. Só leitura da estrutura."""

import os
import re
from dataclasses import dataclass, field
from typing import cast

from pypdf import PasswordType, PdfReader
from pypdf.constants import UserAccessPermissions
from pypdf.generic import DictionaryObject, StreamObject

from .annotations import _object_key
from .base import READ, open_reader
from .messages import Message
from .metadata import ReadMetadata
from .pdfa import _declared_identification

# As 14 fontes que todo leitor tem; sem elas embutidas, o leitor usa uma equivalente.
_STANDARD_14 = {
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Symbol", "ZapfDingbats",
}

_FONT_KINDS = {
    "/Type1": "Type 1",
    "/MMType1": "Type 1 (multiple master)",
    "/TrueType": "TrueType",
    "/Type3": "Type 3",
    "/CIDFontType0": "Type 1 (CID)",
    "/CIDFontType2": "TrueType (CID)",
}

# Chave, bit de /P. A interface dá o nome de cada uma.
PERMISSIONS = [
    ("print", UserAccessPermissions.PRINT),
    ("print_high_quality", UserAccessPermissions.PRINT_TO_REPRESENTATION),
    ("modify", UserAccessPermissions.MODIFY),
    ("copy", UserAccessPermissions.EXTRACT),
    ("accessibility", UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS),
    ("annotate", UserAccessPermissions.ADD_OR_MODIFY),
    ("fill_forms", UserAccessPermissions.FILL_FORM_FIELDS),
    ("assemble", UserAccessPermissions.ASSEMBLE_DOC),
]


@dataclass
class FontInfo:
    name: str  # sem o prefixo de subconjunto ("ABCDEF+")
    kind: str
    embedded: bool
    subset: bool
    standard: bool  # uma das 14 padrão, não embutida
    encoding: str
    pages: list[int] = field(default_factory=list)  # a partir de 0


@dataclass
class PageSizeGroup:
    width: float  # pontos, como a página aparece (área visível, com a /Rotate)
    height: float
    pages: list[int] = field(default_factory=list)


@dataclass
class DocumentProperties:
    version: str
    page_count: int
    file_size: int
    metadata: dict
    linearized: bool
    tagged: bool
    pdfa: str  # "PDF/A-2B", ou vazio se não declara
    form_fields: int
    xfa: bool
    encryption: str  # "AES-256", "RC4-40"...; vazio sem proteção
    needs_password: bool  # senha para abrir
    permissions: dict[str, bool] | None  # None sem proteção
    fonts: list[FontInfo]
    page_sizes: list[PageSizeGroup]


def _version(reader: PdfReader) -> str:
    match = re.match(r"%PDF-(\d+\.\d+)", reader.pdf_header or "")
    version = match.group(1) if match else ""
    catalog_version = str(reader.root_object.get("/Version", "")).lstrip("/")
    if re.fullmatch(r"\d+\.\d+", catalog_version):
        # O /Version do catálogo vale quando é mais novo que o cabeçalho (atualização incremental).
        if not version or tuple(map(int, catalog_version.split("."))) > tuple(map(int, version.split("."))):
            version = catalog_version
    return version


def _encryption(encrypt) -> str:
    encrypt = encrypt.get_object()
    if str(encrypt.get("/Filter", "")) != "/Standard":
        return str(encrypt.get("/Filter", "")).lstrip("/")
    stream_filter = encrypt.get("/StmF", "/Identity")
    filters = encrypt.get("/CF") or {}
    method = str(filters[stream_filter].get_object().get("/CFM", "")) if stream_filter in filters else ""
    if int(encrypt.get("/V", 0)) == 5 or method == "/AESV3":
        return "AES-256"
    if method == "/AESV2":
        return "AES-128"
    return f"RC4-{int(encrypt.get('/Length', 40))}"


def _font_info(font) -> FontInfo:
    subtype = str(font.get("/Subtype", ""))
    descriptor_owner = font
    kind = _FONT_KINDS.get(subtype, subtype.lstrip("/"))
    if subtype == "/Type0":
        descendants = font.get("/DescendantFonts")
        descriptor_owner = descendants[0].get_object() if descendants else DictionaryObject()
        kind = _FONT_KINDS.get(str(descriptor_owner.get("/Subtype", "")), "Type 0")
    descriptor = descriptor_owner.get("/FontDescriptor")
    descriptor = descriptor.get_object() if descriptor is not None else DictionaryObject()
    font_file3 = descriptor.get("/FontFile3")
    if font_file3 is not None and str(font_file3.get_object().get("/Subtype", "")) == "/OpenType":
        kind = "OpenType"
    embedded = subtype == "/Type3" or any(k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3"))

    name = str(font.get("/BaseFont", "") or font.get("/Name", "")).lstrip("/")
    subset = bool(re.match(r"[A-Z]{6}\+", name))
    if subset:
        name = name[7:]

    encoding = font.get("/Encoding")
    if encoding is None:
        encoding_name = ""
    elif isinstance(encoding.get_object(), DictionaryObject):
        base = encoding.get_object().get("/BaseEncoding")
        encoding_name = str(base).lstrip("/") if base else Message("Personalizada")
    else:
        encoding_name = str(encoding.get_object()).lstrip("/")
    return FontInfo(
        name=name,
        kind=kind,
        embedded=embedded,
        subset=subset,
        standard=not embedded and name in _STANDARD_14,
        encoding=encoding_name,
    )


_NAME = rb"/([^\s/\[\]()<>{}%]+)"
_FONT_USE = re.compile(_NAME + rb"\s+[-+\d.]+\s+Tf")
_XOBJECT_USE = re.compile(_NAME + rb"\s+Do\b")


def _used_names(content: bytes | None, pattern) -> set[str] | None:
    """Os recursos que o conteúdo usa ("/F1"), ou None se não deu para ler o conteúdo."""
    if content is None:
        return None
    return {"/" + name.decode("latin-1") for name in pattern.findall(content)}


def _collect_fonts(resources, content: bytes | None, page_index: int, fonts: dict, visited: set) -> None:
    """Fontes que `content` seleciona (Tf), também dentro dos formulários que ele desenha
    (Do): os recursos de uma página podem listar fontes que ela não usa (o reportlab põe
    as do documento inteiro em todas)."""
    resources = resources.get_object() if resources is not None else None
    if not isinstance(resources, DictionaryObject):
        return
    used_fonts = _used_names(content, _FONT_USE)
    for name, reference in cast(DictionaryObject, (resources.get("/Font") or DictionaryObject()).get_object()).items():
        if used_fonts is not None and name not in used_fonts:
            continue
        key = _object_key(reference)
        if key not in fonts:
            fonts[key] = _font_info(reference.get_object())
        if page_index not in fonts[key].pages:
            fonts[key].pages.append(page_index)
    used_xobjects = _used_names(content, _XOBJECT_USE)
    for name, reference in cast(DictionaryObject, (resources.get("/XObject") or DictionaryObject()).get_object()).items():
        xobject = reference.get_object()
        key = _object_key(reference)
        if (used_xobjects is not None and name not in used_xobjects) or key in visited:
            continue
        if str(xobject.get("/Subtype", "")) != "/Form":
            continue
        visited.add(key)  # formulários aninhados ou repetidos: uma vez por página
        _collect_fonts(xobject.get("/Resources"), _data(xobject), page_index, fonts, visited)


def _data(stream) -> bytes | None:
    try:
        return stream.get_data() if stream is not None else b""
    except Exception:
        return None  # filtro desconhecido: conta todas as fontes dos recursos


def _appearance_streams(page):
    """As aparências normais das anotações da página (campos de formulário, carimbos)."""
    for reference in page.get("/Annots", None) or []:
        appearance = reference.get_object().get("/AP")
        normal = appearance.get_object().get("/N") if appearance is not None else None
        if normal is None:
            continue
        normal = normal.get_object()
        if isinstance(normal, StreamObject):
            yield normal
        elif isinstance(normal, DictionaryObject):
            yield from (state.get_object() for state in normal.values() if isinstance(state.get_object(), StreamObject))


def _merge_fonts(fonts) -> list[FontInfo]:
    """Uma linha por fonte: subconjuntos da mesma fonte (um por página, comum em PDFs
    montados) viram uma só, com as páginas de todos."""
    merged: dict[tuple, FontInfo] = {}
    for font in fonts:
        key = (font.name, font.kind, font.embedded, font.subset, str(font.encoding))
        if key in merged:
            merged[key].pages = sorted(set(merged[key].pages) | set(font.pages))
        else:
            merged[key] = font
    return sorted(merged.values(), key=lambda f: (f.name.lower(), f.kind))


def _visible_size(page) -> tuple[float, float]:
    box = page.cropbox
    width, height = abs(float(box.width)), abs(float(box.height))
    return (height, width) if (page.rotation or 0) % 180 else (width, height)


class ReadDocumentProperties:
    def run(self, input_path: str) -> DocumentProperties:
        reader = open_reader(input_path, purpose=READ)
        catalog = reader.root_object

        with open(input_path, "rb") as file:
            linearized = b"/Linearized" in file.read(1024)

        encryption, needs_password, permissions = "", False, None
        if reader.is_encrypted:
            encryption = _encryption(reader.trailer["/Encrypt"])
            needs_password = PdfReader(input_path).decrypt("") == PasswordType.NOT_DECRYPTED
            allowed = reader.user_access_permissions
            permissions = {key: allowed is None or bool(allowed & bit) for key, bit in PERMISSIONS}

        fonts: dict = {}
        sizes: list[PageSizeGroup] = []
        for page_index, page in enumerate(reader.pages):
            visited: set = set()
            _collect_fonts(page.get("/Resources"), _data(page.get_contents()), page_index, fonts, visited)
            for stream in _appearance_streams(page):
                _collect_fonts(stream.get("/Resources"), _data(stream), page_index, fonts, visited)
            width, height = _visible_size(page)
            # Frações de ponto (escaneados, PDFs montados) não são outro tamanho de página.
            group = next((g for g in sizes if abs(g.width - width) <= 2 and abs(g.height - height) <= 2), None)
            if group is None:
                group = PageSizeGroup(round(width, 1), round(height, 1))
                sizes.append(group)
            group.pages.append(page_index)

        try:
            fields = reader.get_fields() or {}
        except Exception:
            fields = {}
        acroform = catalog.get("/AcroForm")
        part, conformance = _declared_identification(reader)
        return DocumentProperties(
            version=_version(reader),
            page_count=len(reader.pages),
            file_size=os.path.getsize(input_path),
            metadata=ReadMetadata().run(input_path),
            linearized=linearized,
            tagged=bool((catalog.get("/MarkInfo") or {}).get("/Marked", False)),
            pdfa=f"PDF/A-{part}{conformance or ''}" if part else "",
            form_fields=len(fields),
            xfa=acroform is not None and "/XFA" in acroform.get_object(),
            encryption=encryption,
            needs_password=needs_password,
            permissions=permissions,
            fonts=_merge_fonts(fonts.values()),
            page_sizes=sizes,
        )
