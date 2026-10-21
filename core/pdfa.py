"""Conversão para PDF/A (arquivamento, ISO 19005) e verificação.

Antes, esta ferramenta gravava a declaração "este arquivo é PDF/A" no XMP (substituindo o
XMP inteiro, com título e autor) sem perfil de cor, sem olhar fontes nem transparência, e o
validador só procurava a própria declaração — todo arquivo gerado aqui "passava". Agora:

- A conversão corrige o que dá para corrigir com segurança — tira JavaScript e ações
  proibidas, ações automáticas (/AA), XFA, anexos que a parte escolhida não permite, recodifica
  streams LZW, acerta os sinalizadores das anotações, embute um perfil de cor sRGB no
  `/OutputIntent` e sincroniza o XMP com o dicionário Info (mesclando com o XMP existente) —
  e depois verifica o que não dá para corrigir sem reescrever o conteúdo: fontes não
  embutidas, transparência (PDF/A-1), camadas (PDF/A-1), documento sem estrutura (nível A),
  texto sem mapeamento Unicode (níveis A e U), anotações sem aparência.
- Se sobrar algum desses problemas, **nada é gravado** e o resultado lista o que impede a
  conversão. A declaração PDF/A só é gravada quando a verificação passa.
- Com o Ghostscript instalado, `use_ghostscript=True` faz a conversão completa (ele embute
  fontes e achata transparência); o resultado passa pela mesma verificação.
- A verificação é parcial: cobre os requisitos acima, não a norma inteira. Com o veraPDF
  instalado (o validador de referência), `ValidatePDFA` também roda ele e informa o
  veredito oficial.

O perfil de cor é o "sRGB v2 micro" do projeto Compact-ICC-Profiles, de domínio público (CC0,
ver `data/icc/LICENSE-Compact-ICC-Profiles.txt`): um perfil ICC v2 válido em todas as partes,
inclusive na PDF/A-1.
"""

import datetime
import mimetypes
import re
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    NameObject,
    NumberObject,
    StreamObject,
    TextStringObject,
)
from pypdf.xmp import XmpInformation

from .base import PDFOperation, add_object, atomic_output, open_reader
from .external import find_ghostscript, find_program, run_cancellable
from .messages import Message
from .progress import Progress, ensure_progress

ICC_PROFILE = Path(__file__).resolve().parent / "data" / "icc" / "sRGB-v2-micro.icc"
_OUTPUT_CONDITION = "sRGB IEC61966-2.1"
PRODUCER = "OpenFolio PDF Suite"

VALID_CONFORMANCE = {1: ("A", "B"), 2: ("A", "B", "U"), 3: ("A", "B", "U")}

# ISO 19005-1 6.6.1 e 19005-2 6.6.1.
_FORBIDDEN_ACTIONS = {
    "/Launch", "/Sound", "/Movie", "/ResetForm", "/ImportData", "/Hide", "/SetOCGState",
    "/Rendition", "/Trans", "/GoTo3DView", "/JavaScript", "/RichMediaExecute", "/SetState", "/NoOp",
}
_FORBIDDEN_ANNOTATIONS = {"/Sound", "/Movie", "/Screen", "/3D", "/RichMedia"}
# Sinalizadores de anotação (ISO 32000-1, tabela 165).
_FLAG_INVISIBLE, _FLAG_HIDDEN, _FLAG_PRINT, _FLAG_NOVIEW, _FLAG_TOGGLENOVIEW = 1, 2, 4, 32, 256
_HIDING_FLAGS = _FLAG_INVISIBLE | _FLAG_HIDDEN | _FLAG_NOVIEW | _FLAG_TOGGLENOVIEW
_GHOSTSCRIPT_TIMEOUT = 600


@dataclass
class PDFAConversionResult:
    written: bool  # False: sobraram problemas (issues) e nada foi gravado
    issues: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)  # o que foi corrigido no caminho
    used_ghostscript: bool = False


@dataclass
class PDFAValidationResult:
    is_valid: bool
    issues: list[str] = field(default_factory=list)
    verapdf_used: bool = False
    verapdf_compliant: bool | None = None  # veredito do veraPDF, quando ele roda


def _check_part(part: int, conformance: str) -> str:
    if part not in VALID_CONFORMANCE:
        raise ValueError(Message("Parte PDF/A inválida: {part} (use 1, 2 ou 3).", part=part))
    conformance = conformance.upper()
    if conformance not in VALID_CONFORMANCE[part]:
        raise ValueError(
            Message(
                "O nível {conformance} não existe no PDF/A-{part} (use {options}).",
                conformance=conformance,
                part=part,
                options=", ".join(VALID_CONFORMANCE[part]),
            )
        )
    return conformance


class ConvertToPDFA(PDFOperation):
    """Converte para PDF/A-`part` nível `conformance` (ver o docstring do módulo)."""

    def run(
        self,
        input_path: str,
        output_path: str,
        part: int = 2,
        conformance: str = "B",
        use_ghostscript: bool = False,
        progress: Progress | None = None,
    ) -> PDFAConversionResult:
        progress = ensure_progress(progress)
        conformance = _check_part(part, conformance)
        reader = open_reader(input_path)

        progress.update(0, 0, "Preparando o documento")
        writer = PdfWriter(clone_from=reader)
        fixed = _prepare(writer, part)

        if use_ghostscript:
            gs_path = find_ghostscript()
            if not gs_path:
                raise RuntimeError("Ghostscript não encontrado. Instale o Ghostscript ou desmarque a opção.")
            progress.update(0, 0, "Convertendo com o Ghostscript")
            with tempfile.TemporaryDirectory() as tmp_dir:
                prepared = Path(tmp_dir) / "preparado.pdf"
                with open(prepared, "wb") as f:
                    writer.write(f)
                converted = Path(tmp_dir) / "pdfa.pdf"
                _ghostscript_pdfa(gs_path, str(prepared), str(converted), part, progress)
                writer = PdfWriter(clone_from=PdfReader(str(converted)))
                fixed += _prepare(writer, part)

        issues = _blocking_issues(writer, part, conformance)
        if issues:
            return PDFAConversionResult(written=False, issues=issues, fixed=fixed, used_ghostscript=use_ghostscript)

        _write_identification(writer, part, conformance)
        progress.check()
        with atomic_output(output_path) as temp_path:
            with open(temp_path, "wb") as f:
                writer.write(f)
        return PDFAConversionResult(written=True, fixed=fixed, used_ghostscript=use_ghostscript)


class ValidatePDFA(PDFOperation):
    """Verifica os requisitos de PDF/A que esta ferramenta cobre (ver o docstring do
    módulo) e, com o veraPDF instalado, roda também a validação completa dele."""

    def run(
        self,
        input_path: str,
        part: int | None = None,
        conformance: str | None = None,
        use_verapdf: bool = True,
        progress: Progress | None = None,
    ) -> PDFAValidationResult:
        progress = ensure_progress(progress)
        reader = PdfReader(input_path)  # PDF criptografado é uma falha a reportar, não uma exceção
        if reader.is_encrypted:
            return PDFAValidationResult(
                is_valid=False, issues=[Message("O PDF está protegido por senha — PDF/A não permite criptografia.")]
            )

        declared_part, declared_conformance = _declared_identification(reader)
        issues: list[str] = []
        if declared_part is None:
            issues.append(Message("Os metadados XMP não declaram conformidade PDF/A."))
        if part is not None and declared_part is not None and declared_part != part:
            issues.append(Message("O arquivo declara PDF/A-{declared}, não PDF/A-{part}.", declared=declared_part, part=part))
        if conformance and declared_conformance and declared_conformance != conformance.upper():
            issues.append(
                Message(
                    "O arquivo declara o nível {declared}, não o nível {conformance}.",
                    declared=declared_conformance,
                    conformance=conformance.upper(),
                )
            )
        check_part = part or declared_part or 2
        check_conformance = (conformance or declared_conformance or "B").upper()
        if check_conformance not in VALID_CONFORMANCE.get(check_part, ()):
            check_conformance = "B"
        progress.update(0, 0, "Verificando o documento")
        issues += _forbidden_content(reader, check_part)
        issues += _blocking_issues(reader, check_part, check_conformance)
        issues += _metadata_issues(reader)

        result = PDFAValidationResult(is_valid=not issues, issues=issues)
        verapdf = find_verapdf() if use_verapdf else None
        if verapdf:
            progress.update(0, 0, "Validando com o veraPDF")
            compliant, failures = _run_verapdf(verapdf, input_path, check_part, check_conformance, progress)
            result.verapdf_used = True
            result.verapdf_compliant = compliant
            if compliant is False:
                result.is_valid = False
                result.issues += [Message("veraPDF: {rule}", rule=failure) for failure in failures]
        return result


# --- Correções -------------------------------------------------------------------------


def _resolve(value):
    return value.get_object() if value is not None and hasattr(value, "get_object") else value


def _is_forbidden_action(action) -> bool:
    action = _resolve(action)
    return isinstance(action, DictionaryObject) and action.get("/S") in _FORBIDDEN_ACTIONS


def _clean_action(holder: DictionaryObject, key: str) -> int:
    """Tira as ações proibidas de `holder[key]` (e da cadeia /Next). Devolve quantas saíram."""
    if key not in holder:
        return 0
    action = _resolve(holder[key])
    if not isinstance(action, DictionaryObject) or "/S" not in action:
        return 0  # /OpenAction pode ser um destino (array), que é permitido
    removed = 0
    if "/Next" in action:
        next_actions = _resolve(action["/Next"])
        if isinstance(next_actions, ArrayObject):
            kept = ArrayObject(item for item in next_actions if not _is_forbidden_action(item))
            removed += len(next_actions) - len(kept)
            if kept:
                action[NameObject("/Next")] = kept
            else:
                del action["/Next"]
        else:
            removed += _clean_action(action, "/Next")
    if action.get("/S") in _FORBIDDEN_ACTIONS:
        del holder[key]
        removed += 1
    return removed


def _embedded_is_pdfa(file_spec) -> bool:
    embedded = _resolve(_resolve(file_spec).get("/EF", {}).get("/F")) if isinstance(_resolve(file_spec), DictionaryObject) else None
    if embedded is None:
        return False
    try:
        data = embedded.get_data()
    except Exception:
        return False
    return data.startswith(b"%PDF") and b"pdfaid:part" in data


def _prepare(writer: PdfWriter, part: int) -> list[str]:
    """Aplica as correções seguras e devolve a lista do que foi feito."""
    fixed: list[str] = []
    counts = {"actions": 0, "attachments": 0, "annotations": 0, "lzw": 0, "flags": 0}
    catalog = writer.root_object

    for key in ("/AA",):
        if key in catalog:
            del catalog[key]
            counts["actions"] += 1
    counts["actions"] += _clean_action(catalog, "/OpenAction")
    names = _resolve(catalog.get("/Names"))
    if isinstance(names, DictionaryObject):
        if "/JavaScript" in names:
            del names["/JavaScript"]
            counts["actions"] += 1
        if "/EmbeddedFiles" in names:
            counts["attachments"] += _filter_embedded_files(writer, names, part)

    acroform = _resolve(catalog.get("/AcroForm"))
    if isinstance(acroform, DictionaryObject):
        if "/XFA" in acroform:
            del acroform["/XFA"]
            fixed.append(Message("Formulário XFA removido (proibido em PDF/A)."))
        if acroform.get("/NeedAppearances"):
            del acroform["/NeedAppearances"]
        for field_ref in _walk_fields(acroform.get("/Fields")):
            field_obj = _resolve(field_ref)
            if "/AA" in field_obj:
                del field_obj["/AA"]
                counts["actions"] += 1
            counts["actions"] += _clean_action(field_obj, "/A")

    for outline in _walk_outlines(catalog.get("/Outlines")):
        counts["actions"] += _clean_action(outline, "/A")

    for page in writer.pages:
        if "/AA" in page:
            del page["/AA"]
            counts["actions"] += 1
        if "/Annots" not in page:
            continue
        kept = ArrayObject()
        for ref in _resolve(page["/Annots"]) or []:
            annotation = _resolve(ref)
            if not isinstance(annotation, DictionaryObject):
                continue
            subtype = annotation.get("/Subtype")
            if subtype in _FORBIDDEN_ANNOTATIONS or (
                subtype == "/FileAttachment" and (part == 1 or (part == 2 and not _embedded_is_pdfa(annotation.get("/FS"))))
            ):
                counts["annotations"] += 1
                continue
            flags = int(annotation.get("/F", 0))
            if subtype == "/Popup":
                if flags & _HIDING_FLAGS and "/F" in annotation:
                    del annotation["/F"]  # balão de comentário: o leitor mostra ao clicar na nota
            elif flags & _HIDING_FLAGS:
                counts["annotations"] += 1  # anotação escondida: não aparece nem na impressão
                continue
            elif not flags & _FLAG_PRINT:
                annotation[NameObject("/F")] = NumberObject(flags | _FLAG_PRINT)
                counts["flags"] += 1
            if "/AA" in annotation:
                del annotation["/AA"]
                counts["actions"] += 1
            counts["actions"] += _clean_action(annotation, "/A")
            kept.append(ref)
        page[NameObject("/Annots")] = kept

    counts["lzw"] = _recode_lzw(writer)
    _ensure_output_intent(writer)
    _sync_metadata(writer)

    if counts["actions"]:
        fixed.append(Message("{count} ação(ões) proibida(s) removida(s) (JavaScript, abrir programas, ações automáticas).", count=counts["actions"]))
    if counts["attachments"]:
        fixed.append(Message("{count} anexo(s) removido(s): o PDF/A-{part} não permite esses anexos.", count=counts["attachments"], part=part))
    if counts["annotations"]:
        fixed.append(Message("{count} anotação(ões) removida(s) (multimídia, escondidas ou com anexo não permitido).", count=counts["annotations"]))
    if counts["flags"]:
        fixed.append(Message("{count} anotação(ões) marcada(s) para impressão, como o PDF/A exige.", count=counts["flags"]))
    if counts["lzw"]:
        fixed.append(Message("{count} stream(s) com compressão LZW recodificado(s).", count=counts["lzw"]))
    return fixed


def _walk_fields(fields):
    stack = list(_resolve(fields) or [])
    seen: set[int] = set()
    while stack:
        ref = stack.pop()
        obj = _resolve(ref)
        if not isinstance(obj, DictionaryObject) or id(obj) in seen:
            continue
        seen.add(id(obj))
        yield obj
        stack.extend(_resolve(obj.get("/Kids")) or [])


def _walk_outlines(outlines):
    root = _resolve(outlines)
    if not isinstance(root, DictionaryObject):
        return
    stack = [root.get("/First")]
    seen: set[int] = set()
    while stack:
        item = _resolve(stack.pop())
        if not isinstance(item, DictionaryObject) or id(item) in seen:
            continue
        seen.add(id(item))
        yield item
        stack.append(item.get("/Next"))
        stack.append(item.get("/First"))


def _filter_embedded_files(writer: PdfWriter, names: DictionaryObject, part: int) -> int:
    """PDF/A-1: nenhum anexo. PDF/A-2: só anexos que sejam PDF/A. PDF/A-3: qualquer um,
    com /AFRelationship e tipo MIME, e listados no /AF do catálogo."""
    tree = _resolve(names["/EmbeddedFiles"])
    entries = list(_name_tree_entries(tree))
    if part == 1:
        del names["/EmbeddedFiles"]
        return len(entries)
    kept = []
    for key, spec_ref in entries:
        if part == 2 and not _embedded_is_pdfa(spec_ref):
            continue
        kept.append((key, spec_ref))
    removed = len(entries) - len(kept)
    if removed:
        flat = ArrayObject()
        for key, spec_ref in kept:
            flat.extend([TextStringObject(str(key)), spec_ref])
        if kept:
            names[NameObject("/EmbeddedFiles")] = add_object(writer, DictionaryObject({NameObject("/Names"): flat}))
        else:
            del names["/EmbeddedFiles"]
    if part == 3 and kept:
        associated = ArrayObject()
        for key, spec_ref in kept:
            spec = _resolve(spec_ref)
            if "/AFRelationship" not in spec:
                spec[NameObject("/AFRelationship")] = NameObject("/Unspecified")
            embedded = _resolve(_resolve(spec.get("/EF", {})).get("/F"))
            if isinstance(embedded, StreamObject) and "/Subtype" not in embedded:
                mime = mimetypes.guess_type(str(spec.get("/UF") or spec.get("/F") or key))[0] or "application/octet-stream"
                embedded[NameObject("/Subtype")] = NameObject("/" + mime)
            associated.append(spec_ref)
        writer.root_object[NameObject("/AF")] = associated
    return removed


def _name_tree_entries(node, seen=None):
    seen = seen if seen is not None else set()
    node = _resolve(node)
    if not isinstance(node, DictionaryObject) or id(node) in seen:
        return
    seen.add(id(node))
    values = _resolve(node.get("/Names")) or []
    for index in range(0, len(values) - 1, 2):
        yield values[index], values[index + 1]
    for kid in _resolve(node.get("/Kids")) or []:
        yield from _name_tree_entries(kid, seen)


def _recode_lzw(writer: PdfWriter) -> int:
    """PDF/A-1 e PDF/A-2 proíbem LZW: os streams são recodificados em Flate (sem perda)."""
    recoded = 0
    for obj in _all_objects(writer):
        if isinstance(obj, StreamObject) and "/LZWDecode" in _filter_names(obj):
            data = obj.get_data()
            if "/DecodeParms" in obj:
                del obj["/DecodeParms"]
            obj._data = zlib.compress(data)
            obj[NameObject("/Filter")] = NameObject("/FlateDecode")
            if hasattr(obj, "decoded_self"):
                obj.decoded_self = None
            recoded += 1
    return recoded


def _filter_names(obj) -> list[str]:
    filters = _resolve(obj.get("/Filter"))
    if filters is None:
        return []
    if isinstance(filters, ArrayObject):
        return [str(f) for f in filters]
    return [str(filters)]


def _all_objects(document):
    """Todos os objetos alcançáveis a partir do catálogo (sem repetir)."""
    root = document.root_object
    stack = [root]
    seen: set[int] = set()
    while stack:
        obj = _resolve(stack.pop())
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, DictionaryObject):
            yield obj
            stack.extend(obj.values())
        elif isinstance(obj, ArrayObject):
            stack.extend(obj)


def _ensure_output_intent(writer: PdfWriter) -> None:
    catalog = writer.root_object
    intents = _resolve(catalog.get("/OutputIntents")) or ArrayObject()
    for intent in intents:
        intent = _resolve(intent)
        if intent.get("/S") == "/GTS_PDFA1" and "/DestOutputProfile" in intent:
            return
    profile = StreamObject()
    profile.set_data(ICC_PROFILE.read_bytes())
    profile = profile.flate_encode()
    profile[NameObject("/N")] = NumberObject(3)
    intent = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/OutputIntent"),
            NameObject("/S"): NameObject("/GTS_PDFA1"),
            NameObject("/OutputConditionIdentifier"): TextStringObject(_OUTPUT_CONDITION),
            NameObject("/RegistryName"): TextStringObject("http://www.color.org"),
            NameObject("/Info"): TextStringObject(_OUTPUT_CONDITION),
            NameObject("/DestOutputProfile"): add_object(writer, profile),
        }
    )
    intents = ArrayObject(list(intents) + [add_object(writer, intent)])
    catalog[NameObject("/OutputIntents")] = intents


def _pdf_date(value) -> datetime.datetime | None:
    match = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?", str(value or ""))
    if not match:
        return None
    year, month, day, hour, minute, second, sign, tz_hour, tz_minute = match.groups()
    offset = datetime.timedelta(0)
    if sign in ("+", "-") and tz_hour:
        offset = datetime.timedelta(hours=int(tz_hour), minutes=int(tz_minute or 0))
        offset = -offset if sign == "-" else offset
    try:
        return datetime.datetime(
            int(year), int(month or 1), int(day or 1), int(hour or 0), int(minute or 0), int(second or 0),
            tzinfo=datetime.timezone(offset),
        ).astimezone(datetime.timezone.utc)
    except ValueError:
        return None


def _info_date(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.timezone.utc).strftime("D:%Y%m%d%H%M%SZ")


def _sync_metadata(writer: PdfWriter) -> None:
    """Info e XMP com os mesmos valores (o PDF/A exige), mantendo o resto do XMP existente.
    As datas vão em UTC nos dois, para não haver diferença de fuso entre eles."""
    info = dict(writer.metadata or {})
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    created = _pdf_date(info.get("/CreationDate")) or now
    xmp = writer.xmp_metadata or XmpInformation.create()

    text = {key: str(info.get(key) or "") for key in ("/Title", "/Author", "/Subject", "/Keywords", "/Creator")}
    xmp.dc_title = {"x-default": text["/Title"]} if text["/Title"] else None
    xmp.dc_creator = [text["/Author"]] if text["/Author"] else None
    xmp.dc_description = {"x-default": text["/Subject"]} if text["/Subject"] else None
    xmp.pdf_keywords = text["/Keywords"] or None
    xmp.xmp_creator_tool = text["/Creator"] or None
    xmp.pdf_producer = PRODUCER
    xmp.xmp_create_date = created
    xmp.xmp_modify_date = now
    xmp.xmp_metadata_date = now
    writer.xmp_metadata = xmp

    updated: dict[str, Any] = {key: value for key, value in text.items() if value}
    updated.update({"/Producer": PRODUCER, "/CreationDate": _info_date(created), "/ModDate": _info_date(now)})
    if "/Trapped" in info:
        updated["/Trapped"] = info["/Trapped"]
    writer.metadata = None
    writer.add_metadata(updated)


def _write_identification(writer: PdfWriter, part: int, conformance: str) -> None:
    xmp = writer.xmp_metadata or XmpInformation.create()
    xmp.pdfaid_part = str(part)
    xmp.pdfaid_conformance = conformance
    writer.xmp_metadata = xmp


# --- Verificação -----------------------------------------------------------------------


def _declared_identification(reader: PdfReader) -> tuple[int | None, str | None]:
    try:
        xmp = reader.xmp_metadata
    except Exception:
        return None, None
    if xmp is None:
        return None, None
    try:
        part = int(xmp.pdfaid_part) if xmp.pdfaid_part is not None else None
    except (TypeError, ValueError):
        part = None
    conformance = str(xmp.pdfaid_conformance).upper() if xmp.pdfaid_conformance else None
    return part, conformance


def _forbidden_content(document, part: int) -> list[str]:
    """O que `_prepare` corrigiria: usado só na verificação de um arquivo pronto."""
    found: set[str] = set()
    catalog = document.root_object
    names = _resolve(catalog.get("/Names"))
    if isinstance(names, DictionaryObject):
        if "/JavaScript" in names:
            found.add(Message("O documento contém JavaScript."))
        if "/EmbeddedFiles" in names and part == 1:
            found.add(Message("O documento contém anexos, proibidos em PDF/A-1."))
        elif "/EmbeddedFiles" in names and part == 2:
            if any(not _embedded_is_pdfa(spec) for _key, spec in _name_tree_entries(names["/EmbeddedFiles"])):
                found.add(Message("O documento contém anexos que não são PDF/A, proibidos em PDF/A-2."))
    if "/AA" in catalog:
        found.add(Message("O documento tem ações automáticas (/AA)."))
    acroform = _resolve(catalog.get("/AcroForm"))
    if isinstance(acroform, DictionaryObject):
        if "/XFA" in acroform:
            found.add(Message("O documento contém um formulário XFA."))
        if acroform.get("/NeedAppearances"):
            found.add(Message("O formulário pede ao leitor que gere as aparências dos campos (/NeedAppearances)."))
    for obj in _all_objects(document):
        if obj.get("/S") in _FORBIDDEN_ACTIONS:
            found.add(Message("O documento contém ações proibidas em PDF/A (JavaScript, abrir programas, multimídia...)."))
        if obj.get("/Type") == "/Page" and "/AA" in obj:
            found.add(Message("Uma página tem ações automáticas (/AA)."))
        if "/LZWDecode" in _filter_names(obj) and isinstance(obj, StreamObject):
            found.add(Message("O documento usa compressão LZW."))
    for page in document.pages:
        for ref in _resolve(page.get("/Annots")) or []:
            annotation = _resolve(ref)
            if not isinstance(annotation, DictionaryObject):
                continue
            subtype = annotation.get("/Subtype")
            if subtype in _FORBIDDEN_ANNOTATIONS:
                found.add(Message("O documento contém anotações multimídia ou 3D."))
            flags = int(annotation.get("/F", 0))
            if subtype != "/Popup" and (flags & _HIDING_FLAGS or not flags & _FLAG_PRINT):
                found.add(Message("Há anotações escondidas ou que não saem na impressão."))
    return sorted(found)


def _blocking_issues(document, part: int, conformance: str) -> list[str]:
    """O que a conversão não corrige sozinha (fontes, transparência, estrutura...)."""
    issues: list[str] = []
    catalog = document.root_object

    intents = [_resolve(i) for i in _resolve(catalog.get("/OutputIntents")) or []]
    if not any(i.get("/S") == "/GTS_PDFA1" and "/DestOutputProfile" in i for i in intents):
        issues.append(Message("Falta o perfil de cor (/OutputIntent)."))

    fonts, unicode_missing, transparency = _scan_resources(document)
    if fonts:
        issues.append(Message("Fontes não embutidas: {fonts}.", fonts=", ".join(sorted(fonts)[:8])))
    if part == 1 and transparency:
        issues.append(Message("O PDF/A-1 não permite transparência, e o documento usa (escolha a parte 2 ou 3)."))
    if part == 1 and "/OCProperties" in catalog:
        issues.append(Message("O PDF/A-1 não permite camadas, e o documento tem (escolha a parte 2 ou 3)."))
    if conformance in ("A", "U") and unicode_missing:
        issues.append(
            Message(
                "O nível {conformance} exige que o texto tenha mapeamento Unicode, e estas fontes não têm: {fonts}.",
                conformance=conformance,
                fonts=", ".join(sorted(unicode_missing)[:8]),
            )
        )
    if conformance == "A":
        mark_info = _resolve(catalog.get("/MarkInfo"))
        if "/StructTreeRoot" not in catalog or not (isinstance(mark_info, DictionaryObject) and mark_info.get("/Marked")):
            issues.append(Message("O nível A exige um documento tagueado (com estrutura de acessibilidade); use o nível B."))
        if not catalog.get("/Lang"):
            issues.append(Message("O nível A exige o idioma do documento (/Lang); defina-o em Acessibilidade."))

    missing_appearance = 0
    for page in document.pages:
        for ref in _resolve(page.get("/Annots")) or []:
            annotation = _resolve(ref)
            if isinstance(annotation, DictionaryObject) and annotation.get("/Subtype") not in ("/Popup", "/Link"):
                rect = [float(v) for v in annotation.get("/Rect", [0, 0, 0, 0])]
                has_area = abs(rect[2] - rect[0]) > 0 and abs(rect[3] - rect[1]) > 0
                if has_area and "/AP" not in annotation:
                    missing_appearance += 1
    if missing_appearance:
        issues.append(Message("{count} anotação(ões) sem aparência definida (/AP).", count=missing_appearance))
    return issues


_TEXT_SHOWING = {b"Tj", b"TJ", b"'", b'"'}


def _used_fonts(document) -> list[DictionaryObject]:
    """As fontes que de fato desenham texto (um `Tf` seguido de `Tj`/`TJ`), nas páginas e em
    todo Form XObject (inclusive aparências de anotações). Só essas precisam estar embutidas:
    o reportlab, por exemplo, seleciona a Helvetica no começo de toda página sem escrever nada
    com ela."""
    used: dict[int, DictionaryObject] = {}
    sources = [(page.get_contents(), page.get("/Resources")) for page in document.pages]
    sources += [
        (obj, obj.get("/Resources"))
        for obj in _all_objects(document)
        if isinstance(obj, StreamObject) and obj.get("/Subtype") == "/Form"
    ]
    for contents, resources in sources:
        resources = _resolve(resources)
        if contents is None or not isinstance(resources, DictionaryObject):
            continue
        fonts = _resolve(resources.get("/Font"))
        if not isinstance(fonts, DictionaryObject):
            continue
        try:
            operations = ContentStream(contents, None).operations
        except Exception:
            continue
        current = None
        for operands, operator in operations:
            if operator == b"Tf" and operands:
                current = operands[0]
            elif operator in _TEXT_SHOWING and current is not None and current in fonts:
                font = _resolve(fonts[current])
                used[id(font)] = font
    return list(used.values())


def _scan_resources(document) -> tuple[set[str], set[str], bool]:
    """Fontes usadas e não embutidas, fontes usadas sem mapeamento Unicode, e se o
    documento usa transparência."""
    not_embedded: set[str] = set()
    no_unicode: set[str] = set()
    for font in _used_fonts(document):
        subtype = font.get("/Subtype")
        name = str(font.get("/BaseFont", "?")).lstrip("/")
        if subtype == "/Type3":
            continue
        descriptor_holder = font
        if subtype == "/Type0":
            descendants = _resolve(font.get("/DescendantFonts")) or []
            descriptor_holder = _resolve(descendants[0]) if descendants else font
            if "/ToUnicode" not in font:
                no_unicode.add(name)
        descriptor = _resolve(descriptor_holder.get("/FontDescriptor"))
        if not (isinstance(descriptor, DictionaryObject) and any(k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3"))):
            not_embedded.add(name)
        if subtype in ("/TrueType", "/Type1") and "/ToUnicode" not in font and "/Encoding" not in font:
            if isinstance(descriptor, DictionaryObject) and int(descriptor.get("/Flags", 0)) & 4:  # simbólica
                no_unicode.add(name)

    transparency = False
    for obj in _all_objects(document):
        group = _resolve(obj.get("/Group"))
        if isinstance(group, DictionaryObject) and group.get("/S") == "/Transparency":
            transparency = True
        if obj.get("/Subtype") == "/Image" and "/SMask" in obj:
            transparency = True
        # Estado gráfico (/ExtGState, que nem sempre traz o /Type): opacidade, máscara e mistura.
        is_graphics_state = obj.get("/Type") == "/ExtGState" or (
            "/Subtype" not in obj and any(key in obj for key in ("/CA", "/ca", "/BM"))
        )
        if is_graphics_state:
            if any(key in obj and float(obj[key]) < 1 for key in ("/CA", "/ca")):
                transparency = True
            if obj.get("/SMask") not in (None, "/None"):
                transparency = True
            if obj.get("/BM") not in (None, "/Normal", "/Compatible"):
                transparency = True
    return not_embedded, no_unicode, transparency


def _metadata_issues(reader: PdfReader) -> list[str]:
    issues: list[str] = []
    try:
        xmp = reader.xmp_metadata
    except Exception:
        return [Message("Os metadados XMP estão malformados.")]
    if xmp is None:
        return issues
    info: dict = reader.metadata or {}
    title = str(info.get("/Title") or "")
    xmp_title = (xmp.dc_title or {}).get("x-default", "") if isinstance(xmp.dc_title, dict) else ""
    if title != xmp_title:
        issues.append(Message("O título no dicionário Info e no XMP não são iguais."))
    author = str(info.get("/Author") or "")
    xmp_author = ", ".join(xmp.dc_creator or [])
    if author != xmp_author:
        issues.append(Message("O autor no dicionário Info e no XMP não são iguais."))
    return issues


# --- Programas externos ----------------------------------------------------------------


def find_verapdf() -> str | None:
    return find_program(
        [
            "verapdf",
            "verapdf.bat",
            str(Path.home() / "verapdf" / "verapdf.bat"),
            r"C:\Program Files\veraPDF\verapdf.bat",
        ]
    )


def _ps_string(text: str) -> str:
    return "(" + text.replace("\\", "/").replace("(", "\\(").replace(")", "\\)") + ")"


def _ghostscript_pdfa(gs_path: str, input_path: str, output_path: str, part: int, progress: Progress) -> None:
    icc_path = str(ICC_PROFILE).replace("\\", "/")
    with tempfile.TemporaryDirectory() as tmp_dir:
        definition = Path(tmp_dir) / "PDFA_def.ps"
        definition.write_text(
            "%!\n"
            f"/ICCProfile {_ps_string(icc_path)} def\n"
            "[/_objdef {icc_PDFA} /type /stream /OBJ pdfmark\n"
            "[{icc_PDFA} <</N 3>> /PUT pdfmark\n"
            "[{icc_PDFA} ICCProfile (r) file /PUT pdfmark\n"
            "[/_objdef {OutputIntent_PDFA} /type /dict /OBJ pdfmark\n"
            "[{OutputIntent_PDFA} <<\n"
            "  /Type /OutputIntent /S /GTS_PDFA1\n"
            "  /DestOutputProfile {icc_PDFA}\n"
            f"  /OutputConditionIdentifier {_ps_string(_OUTPUT_CONDITION)}\n"
            ">> /PUT pdfmark\n"
            "[{Catalog} <</OutputIntents [ {OutputIntent_PDFA} ]>> /PUT pdfmark\n",
            encoding="ascii",
        )
        command = [
            gs_path,
            f"-dPDFA={part}",
            "-dBATCH",
            "-dNOPAUSE",
            "-dQUIET",
            "-dNOOUTERSAVE",
            "-dPDFACompatibilityPolicy=1",
            "-sColorConversionStrategy=RGB",
            "-sDEVICE=pdfwrite",
            f"--permit-file-read={icc_path}",
            f"-sOutputFile={output_path}",
            str(definition),
            input_path,
        ]
        returncode, stderr = run_cancellable(command, progress, _GHOSTSCRIPT_TIMEOUT, program="O Ghostscript")
    if returncode != 0 or not Path(output_path).is_file():
        detail = stderr.decode(errors="replace").strip() or f"código de saída {returncode}"
        raise RuntimeError(Message("O Ghostscript falhou ao converter para PDF/A: {detail}", detail=detail))


def _run_verapdf(verapdf: str, path: str, part: int, conformance: str, progress: Progress) -> tuple[bool | None, list[str]]:
    """Roda o veraPDF e devolve (conforme?, regras que falharam). (None, []) se a saída não
    puder ser lida."""
    command = [verapdf, "--flavour", f"{part}{conformance.lower()}", "--format", "mrr", path]
    _returncode, output = run_cancellable(command, progress, _GHOSTSCRIPT_TIMEOUT, program="O veraPDF", capture_stdout=True)
    try:
        root = ElementTree.fromstring(output)
    except ElementTree.ParseError:
        return None, []
    compliant = None
    failures: list[str] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "validationReport" and "isCompliant" in element.attrib:
            compliant = element.attrib["isCompliant"] == "true"
        if tag == "rule" and element.attrib.get("status") == "failed":
            description = next((child.text for child in element if child.tag.rsplit("}", 1)[-1] == "description"), "")
            clause = element.attrib.get("clause", "")
            failures.append(f"{clause} {description}".strip())
    return compliant, failures[:20]
