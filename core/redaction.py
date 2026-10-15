"""Redação real (remoção definitiva de conteúdo) e sanitização de PDFs.

Redação: pypdf não tem nenhuma função de redação pronta, e remover só o texto de dentro de
um retângulo exigiria interpretar manualmente o content stream do PDF (matrizes de posição
de texto) — um projeto grande por si só, com risco real de deixar dado "por baixo"
recuperável, que é exatamente o tipo de falha que uma ferramenta de redação existe para
evitar. A abordagem aqui é rasterizar (ver `core/rasterize.py`): a página marcada é
renderizada como aparece na tela, as áreas são pintadas de preto **nos próprios pixels** e a
página inteira vira só essa imagem — não sobra texto, vetor, nem pixel original da área
marcada para recuperar. Depois de gravar, `_verify_redaction` confere o resultado (sem texto,
áreas pretas tanto na imagem embutida quanto no render) antes de o arquivo ocupar o lugar da
saída. Efeito colateral aceito: a página inteira perde a camada de texto pesquisável, não só
a área marcada.

As áreas chegam no espaço do usuário do PDF (o mesmo de `/Rect` e do pdfium) e são
convertidas com `core/geometry.py`, o que faz a redação funcionar também em páginas com
`/Rotate` e CropBox deslocada.

Sanitizar: um PdfWriter novo (sem clone_from) não leva nada do catálogo do documento
original — metadados, XMP, JavaScript de documento, anexos, ações de abertura, formulário
(inclusive XFA). O que vem junto com as páginas é varrido objeto por objeto (`_Sanitizer`):
ações de JavaScript e ações que abrem arquivos/programas, enviam dados ou carregam conteúdo
externo (em `/A`, `/AA` e encadeadas em `/Next`, de anotações, campos, páginas), anotações
com arquivo anexado e multimídia/3D, arquivos embutidos em qualquer lugar e dados privados de
aplicativos. O resultado também passa por uma verificação (`find_residual_risks`) antes de
ser gravado no destino. Não remove conteúdo visível das páginas (texto branco, texto sob
imagens, camadas ocultas continuam no content stream) — isso é papel da redação.
"""

import re
from dataclasses import dataclass

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, StreamObject

from .base import PDFOperation, atomic_output, open_reader, require_valid_page_index
from .geometry import PageGeometry, Rect
from .rasterize import RASTER_SCALE, fill_visual_rects, image_page, render_visual_page, visible_visual_rects

_REDACT_SCALE = RASTER_SCALE
_REDACTION_COLOR = (0, 0, 0)
_DETECTION_PADDING = 1.0  # folga (pt) em volta de cada ocorrência: a suavização da fonte vaza
_VERIFY_RENDER_SCALE = 2.0
_VERIFY_MAX_LEVEL = 24  # tolerância de "preto" no render da verificação (0 = preto puro)

# Padrões comuns de dado sensível para sugestão automática de redação. Todos priorizam
# não deixar passar ocorrência real (a redação em si é sempre revisável/removível da lista
# de pendentes antes de aplicar, então um falso positivo custa pouco; um falso negativo
# custaria o dado vazando).
_PATTERNS: dict[str, re.Pattern] = {
    "cpf": re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b"),
    "cnpj": re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{14}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    # DDI +55 opcional, DDD com ou sem parênteses e o 9 do celular seguido ou não de
    # separador — "(19) 9.9999-9999", com ponto depois do 9, é comum em currículos.
    "phone": re.compile(r"(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?(?:9[\s.-]?)?\d{4}[\s.-]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}

PATTERN_KINDS = tuple(_PATTERNS.keys())
CUSTOM_PATTERN_KIND = "custom"


@dataclass
class RedactionRect:
    """Uma área marcada para redação, no espaço do usuário do PDF (o mesmo de `/Rect` e do
    pdfium — sem `/Rotate` nem CropBox aplicados)."""

    page_index: int
    left: float
    bottom: float
    right: float
    top: float
    kind: str = ""  # padrão que encontrou a área (ver PATTERN_KINDS); vazio = marcada à mão
    text: str = ""  # trecho encontrado, para o usuário revisar antes de aplicar

    def as_rect(self) -> Rect:
        return (self.left, self.bottom, self.right, self.top)


class RedactionVerificationError(RuntimeError):
    """A conferência pós-redação encontrou conteúdo que deveria ter sido apagado."""


class FindSensitiveData(PDFOperation):
    """Busca padrões de dado sensível (CPF, CNPJ, e-mail, telefone, cartão de crédito, ou
    uma expressão regular à parte) no texto do PDF e devolve um `RedactionRect` por
    ocorrência — para revisão do usuário antes de virar redação de verdade.

    Usa `pypdfium2` (já uma dependência do projeto, mesma biblioteca usada para renderizar
    a página que a redação depois rasteriza) para mapear cada caractere encontrado de volta
    a uma caixa em coordenadas PDF, do mesmo jeito que `ui/viewer/search.py` já faz para a
    busca de texto simples do visualizador — só que aqui a ocorrência vem de regex, não de
    string literal, então não dá pra usar a busca nativa do pdfium (que não suporta regex).
    Uma ocorrência que atravessa quebra de linha vira uma única caixa cobrindo as duas
    linhas: isso apenas redige uma área um pouco maior do que o necessário, nunca menor, o
    que é o lado seguro do erro para uma ferramenta de redação.
    """

    def run(
        self,
        input_path: str,
        kinds: list[str] | None = None,
        custom_pattern: str | None = None,
    ) -> list[RedactionRect]:
        open_reader(input_path)  # recusa PDF protegido por senha, mesma checagem das outras operações

        patterns = [(kind, _PATTERNS[kind]) for kind in (kinds or []) if kind in _PATTERNS]
        if custom_pattern:
            try:
                patterns.append((CUSTOM_PATTERN_KIND, re.compile(custom_pattern)))
            except re.error as exc:
                raise ValueError(f"Expressão regular inválida: {exc}") from exc
        if not patterns:
            return []

        rects: list[RedactionRect] = []
        seen: set[tuple] = set()
        pdfium_doc = pdfium.PdfDocument(input_path)
        try:
            for page_index in range(len(pdfium_doc)):
                page = pdfium_doc[page_index]
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                    char_count = textpage.count_chars()
                    for kind, pattern in patterns:
                        for match in pattern.finditer(text):
                            start, end = match.start(), min(match.end(), char_count)
                            if start >= end:
                                continue
                            bounds = _union_of_char_boxes(textpage.get_charbox(i) for i in range(start, end))
                            if bounds is None:
                                continue
                            left, bottom, right, top = bounds
                            key = (page_index, round(left, 2), round(bottom, 2), round(right, 2), round(top, 2))
                            if key in seen:  # dois padrões casando no mesmo trecho
                                continue
                            seen.add(key)
                            rects.append(
                                RedactionRect(
                                    page_index,
                                    left - _DETECTION_PADDING,
                                    bottom - _DETECTION_PADDING,
                                    right + _DETECTION_PADDING,
                                    top + _DETECTION_PADDING,
                                    kind=kind,
                                    text=" ".join(match.group(0).split()),
                                )
                            )
                finally:
                    textpage.close()
        finally:
            pdfium_doc.close()

        return rects


def _union_of_char_boxes(boxes) -> Rect | None:
    """União das caixas dos caracteres, ignorando as de área zero (o pdfium devolve caixas
    vazias para os espaços e quebras de linha que ele mesmo gera entre linhas)."""
    boxes = list(boxes)
    useful = [box for box in boxes if box[2] > box[0] and box[3] > box[1]] or boxes
    if not useful:
        return None
    return (
        min(box[0] for box in useful),
        min(box[1] for box in useful),
        max(box[2] for box in useful),
        max(box[3] for box in useful),
    )


class RedactDocument(PDFOperation):
    """Remove definitivamente o conteúdo das áreas marcadas, achatando a página em imagem
    (ver o docstring do módulo). Devolve quantas páginas foram redigidas."""

    def run(self, input_path: str, output_path: str, rects: list[RedactionRect]) -> int:
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        rects_by_page: dict[int, list[Rect]] = {}
        for rect in rects:
            require_valid_page_index(total_pages, rect.page_index)
            rects_by_page.setdefault(rect.page_index, []).append(rect.as_rect())

        writer = PdfWriter()
        burned: dict[int, list[Rect]] = {}  # página -> áreas pintadas, no espaço visual

        pdfium_doc = pdfium.PdfDocument(input_path)
        try:
            # Campos de formulário aparecem na imagem como aparecem no visualizador.
            pdfium_doc.init_forms()
            for index, page in enumerate(reader.pages):
                page_rects = rects_by_page.get(index)
                if not page_rects:
                    writer.add_page(page)
                    continue

                image, geometry = render_visual_page(pdfium_doc[index], _REDACT_SCALE)
                visual_rects = visible_visual_rects(geometry, page_rects)
                fill_visual_rects(image, geometry, visual_rects, _REDACTION_COLOR)
                writer.add_page(image_page(image, geometry.width, geometry.height))
                burned[index] = visual_rects
        finally:
            pdfium_doc.close()

        with atomic_output(output_path) as temp_path:
            with open(temp_path, "wb") as f:
                writer.write(f)
            _verify_redaction(temp_path, burned)
        return len(burned)


def _verify_redaction(path: str, burned: dict[int, list[Rect]]) -> None:
    """Confere o arquivo redigido antes de ele ser entregue: nenhuma página redigida pode
    ter texto, e cada área marcada precisa estar preta tanto na imagem embutida (o que um
    extrator de imagens recuperaria) quanto no render da página (o que um leitor mostra)."""
    if not burned:
        return

    reader = PdfReader(path)
    document = pdfium.PdfDocument(path)
    try:
        for index, visual_rects in burned.items():
            page = reader.pages[index]
            if page.extract_text().strip():
                raise RedactionVerificationError(
                    f"A página {index + 1} ainda tem texto depois da redação. O arquivo não foi salvo."
                )
            geometry = PageGeometry.from_pypdf_page(page)
            images = [image_file.image.convert("RGB") for image_file in page.images]
            if len(images) != 1:
                raise RedactionVerificationError(
                    f"A página {index + 1} tem conteúdo inesperado depois da redação. O arquivo não foi salvo."
                )
            rendered = document[index].render(scale=_VERIFY_RENDER_SCALE).to_pil().convert("RGB")
            for candidate, max_level in ((images[0], 0), (rendered, _VERIFY_MAX_LEVEL)):
                for rect in visual_rects:
                    if not _area_is_filled(candidate, geometry, rect, max_level):
                        raise RedactionVerificationError(
                            f"Na página {index + 1}, uma área marcada ainda mostra conteúdo depois "
                            "da redação. O arquivo não foi salvo."
                        )
    finally:
        document.close()


def _area_is_filled(image, geometry: PageGeometry, rect: Rect, max_level: int) -> bool:
    x0, y0, x1, y1 = geometry.visual_rect_to_pixels(rect, image.width, image.height)
    # Ignora 1 px de borda: no render, a suavização mistura a tarja com o pixel vizinho.
    x0, y0, x1, y1 = x0 + 1, y0 + 1, x1 - 1, y1 - 1
    if x1 <= x0 or y1 <= y0:
        return True  # área pequena demais para sobrar um pixel interno a conferir
    extrema = image.crop((x0, y0, x1, y1)).getextrema()
    return all(high <= max_level for _low, high in extrema)


# -- sanitização ------------------------------------------------------------------------------

# Ações inofensivas (navegação e exibição). Tudo que não estiver aqui é removido — inclusive
# tipos de ação que surjam em versões futuras do formato.
_SAFE_ACTION_TYPES = {"/GoTo", "/URI", "/Named", "/Hide", "/ResetForm", "/SetOCGState", "/Thread", "/Trans"}
_CODE_ACTION_TYPES = {"/JavaScript", "/RichMediaExecute"}
# Ações perigosas reconhecíveis em qualquer dicionário (só aparecem como valor de /S de ação).
_DANGEROUS_ACTION_TYPES = _CODE_ACTION_TYPES | {
    "/Launch",
    "/SubmitForm",
    "/ImportData",
    "/GoToR",
    "/GoToE",
    "/Rendition",
}
_JAVASCRIPT_URI_SCHEMES = {"javascript", "vbscript"}
_EXTERNAL_URI_SCHEMES = {"file", "data"}
_RISKY_ANNOTATION_SUBTYPES = {"/RichMedia", "/3D", "/Screen", "/Movie", "/Sound"}
_EMBEDDED_FILE_KEYS = ("/F", "/UF", "/DOS", "/Mac", "/Unix")


@dataclass
class SanitizeReport:
    """O que a sanitização removeu, para mostrar ao usuário."""

    javascript: int = 0  # ações e scripts de JavaScript (documento, páginas, anotações, campos)
    external_actions: int = 0  # ações que abrem arquivos/programas, enviam dados ou carregam conteúdo externo
    embedded_files: int = 0  # arquivos embutidos (anexos do documento, de anotações ou associados)
    annotations_removed: int = 0  # anotações removidas (todas, se pedido; senão só multimídia/3D)
    private_data: int = 0  # dados privados de aplicativos (/PieceInfo), miniaturas e XMP de páginas/imagens
    metadata_removed: bool = False
    xfa_removed: bool = False  # formulário XFA, que pode conter scripts

    @property
    def total(self) -> int:
        return (
            self.javascript
            + self.external_actions
            + self.embedded_files
            + self.annotations_removed
            + self.private_data
            + int(self.metadata_removed)
            + int(self.xfa_removed)
        )


class SanitizationVerificationError(RuntimeError):
    """A conferência pós-sanitização encontrou algo que deveria ter sido removido."""


def _resolve(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def _uri_risk(action: DictionaryObject) -> str | None:
    uri = str(action.get("/URI", "") or "")
    scheme = uri.split(":", 1)[0].strip().lower() if ":" in uri else ""
    if scheme in _JAVASCRIPT_URI_SCHEMES:
        return "javascript"
    if scheme in _EXTERNAL_URI_SCHEMES:
        return "external"
    return None


def _classify_action(action: DictionaryObject) -> str | None:
    """"javascript" ou "external" para uma ação que deve sair; None se for segura."""
    action_type = action.get("/S")
    if action_type == "/URI":
        return _uri_risk(action)
    if action_type in _SAFE_ACTION_TYPES:
        return None
    if action_type in _CODE_ACTION_TYPES or "/JS" in action:
        return "javascript"
    return "external"


def _is_action(value) -> bool:
    value = _resolve(value)
    return isinstance(value, DictionaryObject) and "/S" in value


def _is_additional_actions(value) -> bool:
    value = _resolve(value)
    return isinstance(value, DictionaryObject) and all(_is_action(item) for item in value.values())


def _is_embedded_file_spec(obj: DictionaryObject) -> bool:
    embedded = _resolve(obj.get("/EF")) if "/EF" in obj else None
    if not isinstance(embedded, DictionaryObject) or embedded.get("/Type") == "/Font":
        return False
    return any(isinstance(_resolve(embedded.get(key)), StreamObject) for key in _EMBEDDED_FILE_KEYS)


def _is_xmp_stream(value) -> bool:
    value = _resolve(value)
    return isinstance(value, StreamObject) and (
        value.get("/Type") == "/Metadata" or value.get("/Subtype") == "/XML"
    )


def _is_page_or_form(obj: DictionaryObject) -> bool:
    return obj.get("/Type") == "/Page" or obj.get("/Subtype") == "/Form"


def _count_name_tree_entries(node, visited: set[int] | None = None) -> int:
    visited = visited if visited is not None else set()
    node = _resolve(node)
    if not isinstance(node, DictionaryObject) or id(node) in visited:
        return 0
    visited.add(id(node))
    count = len(_resolve(node.get("/Names")) or []) // 2
    for kid in _resolve(node.get("/Kids")) or []:
        count += _count_name_tree_entries(kid, visited)
    return count


class _Sanitizer:
    """Remove o que é perigoso dos objetos do PdfReader antes de as páginas serem copiadas."""

    def __init__(self, report: SanitizeReport, remove_metadata: bool):
        self.report = report
        self.remove_metadata = remove_metadata

    def _count(self, kind: str) -> None:
        if kind == "javascript":
            self.report.javascript += 1
        else:
            self.report.external_actions += 1

    def sanitize_action(self, action_ref, visiting: set[int] | None = None):
        """Devolve a ação (ou sequência de ações) sem os itens perigosos, mantendo a
        referência original para o que sobrar; None se nada sobrar."""
        visiting = visiting if visiting is not None else set()
        action = _resolve(action_ref)
        if isinstance(action, ArrayObject):
            kept = ArrayObject()
            for item in action:
                sanitized = self.sanitize_action(item, visiting)
                if sanitized is not None:
                    kept.append(sanitized)
            return kept or None
        if not isinstance(action, DictionaryObject) or id(action) in visiting:
            return None  # ação malformada, ou um ciclo em /Next
        visiting.add(id(action))

        next_ref = action.raw_get("/Next") if "/Next" in action else None
        sanitized_next = self.sanitize_action(next_ref, visiting) if next_ref is not None else None

        kind = _classify_action(action)
        if kind is not None:
            self._count(kind)
            if isinstance(sanitized_next, ArrayObject):
                # Uma sequência não pode ocupar o lugar de uma ação única (/A, gatilho de /AA).
                return sanitized_next[0] if len(sanitized_next) == 1 else None
            return sanitized_next

        if sanitized_next is None:
            if "/Next" in action:
                del action["/Next"]
        else:
            action[NameObject("/Next")] = sanitized_next
        return action_ref

    def _sanitize_additional_actions(self, holder: DictionaryObject) -> None:
        additional = _resolve(holder["/AA"])
        for trigger in list(additional.keys()):
            sanitized = self.sanitize_action(additional.raw_get(trigger))
            if sanitized is None:
                del additional[trigger]
            else:
                additional[NameObject(trigger)] = sanitized
        if not additional:
            del holder["/AA"]

    def report_document_level(self, reader: PdfReader) -> None:
        """Contabiliza o que vive no catálogo — que não é copiado para o arquivo novo."""
        catalog = reader.trailer["/Root"]
        names = _resolve(catalog.get("/Names"))
        if isinstance(names, DictionaryObject):
            if "/JavaScript" in names:
                self.report.javascript += _count_name_tree_entries(names.raw_get("/JavaScript"))
            if "/EmbeddedFiles" in names:
                self.report.embedded_files += _count_name_tree_entries(names.raw_get("/EmbeddedFiles"))
        if "/OpenAction" in catalog and _is_action(catalog.raw_get("/OpenAction")):
            self.sanitize_action(catalog.raw_get("/OpenAction"))
        if "/AA" in catalog and _is_additional_actions(catalog.raw_get("/AA")):
            self._sanitize_additional_actions(catalog)
        acroform = _resolve(catalog.get("/AcroForm"))
        if isinstance(acroform, DictionaryObject) and "/XFA" in acroform:
            self.report.xfa_removed = True
        if self.remove_metadata and (reader.metadata or "/Metadata" in catalog):
            self.report.metadata_removed = True

    def filter_annotations(self, page, remove_all: bool) -> None:
        if "/Annots" not in page:
            return
        annotations = list(_resolve(page["/Annots"]) or [])
        if remove_all:
            for ref in annotations:
                if _resolve(ref).get("/Subtype") == "/FileAttachment":
                    self.report.embedded_files += 1
                else:
                    self.report.annotations_removed += 1
            del page["/Annots"]
            return

        removed: set[int] = set()
        kept = []
        for ref in annotations:
            annotation = _resolve(ref)
            subtype = annotation.get("/Subtype")
            if subtype == "/FileAttachment":
                self.report.embedded_files += 1
                removed.add(id(annotation))
            elif subtype in _RISKY_ANNOTATION_SUBTYPES:
                self.report.annotations_removed += 1
                removed.add(id(annotation))
            else:
                kept.append(ref)
        if not removed:
            return

        final = ArrayObject()
        for ref in kept:
            annotation = _resolve(ref)
            parent_id = id(_resolve(annotation.get("/Parent"))) if "/Parent" in annotation else None
            if annotation.get("/Subtype") == "/Popup" and parent_id in removed:
                continue  # o balão de comentário da anotação removida
            # Uma referência a uma anotação removida a copiaria de volta para o arquivo novo.
            for key in ("/Popup", "/IRT", "/Parent"):
                if key in annotation and id(_resolve(annotation.raw_get(key))) in removed:
                    del annotation[key]
            final.append(ref)
        if final:
            page[NameObject("/Annots")] = final
        else:
            del page["/Annots"]

    def walk(self, pages) -> None:
        """Varre tudo o que é alcançável a partir das páginas (anotações, campos e seus pais,
        recursos, XObjects) e limpa cada dicionário.

        O pypdf entrega cada página como uma cópia do dicionário original (`reader.pages`),
        e é essa cópia que vai para o arquivo novo. O dicionário original continua
        alcançável pela árvore de páginas (`/Parent` → `/Kids`) ou pelo `/P` das anotações,
        ainda com o estado anterior à filtragem — por isso qualquer outro dicionário de
        página encontrado no caminho é pulado.
        """
        page_ids = {id(page) for page in pages}
        stack = list(pages)
        visited: set[int] = set()
        while stack:
            obj = _resolve(stack.pop())
            if id(obj) in visited:
                continue
            visited.add(id(obj))
            if isinstance(obj, DictionaryObject):
                if obj.get("/Type") == "/Page" and id(obj) not in page_ids:
                    continue
                self._sanitize_dictionary(obj)
                stack.extend(value for key, value in obj.items() if not (id(obj) in page_ids and key == "/Parent"))
            elif isinstance(obj, ArrayObject):
                stack.extend(obj)

    def _sanitize_dictionary(self, obj: DictionaryObject) -> None:
        if obj.get("/S") in _DANGEROUS_ACTION_TYPES or (obj.get("/S") == "/URI" and _uri_risk(obj)):
            # Ação perigosa alcançada por um caminho que não é /A, /AA nem /Next: neutraliza.
            self._count(_classify_action(obj) or "external")
            obj.clear()
            return
        if "/A" in obj and _is_action(obj.raw_get("/A")):
            sanitized = self.sanitize_action(obj.raw_get("/A"))
            if sanitized is None:
                del obj["/A"]
            else:
                obj[NameObject("/A")] = sanitized
        if "/AA" in obj and _is_additional_actions(obj.raw_get("/AA")):
            self._sanitize_additional_actions(obj)
        if "/S" in obj and "/JS" in obj:
            del obj["/JS"]
            self.report.javascript += 1
        if _is_embedded_file_spec(obj):
            del obj["/EF"]
            self.report.embedded_files += 1
        if "/AF" in obj and isinstance(_resolve(obj.get("/AF")), ArrayObject):
            for spec in _resolve(obj["/AF"]):
                spec = _resolve(spec)
                if isinstance(spec, DictionaryObject) and _is_embedded_file_spec(spec):
                    self.report.embedded_files += 1
            del obj["/AF"]
        if _is_page_or_form(obj):
            for key in ("/PieceInfo", "/Thumb"):
                if key in obj:
                    del obj[key]
                    self.report.private_data += 1
        if self.remove_metadata and "/Metadata" in obj and _is_xmp_stream(obj.raw_get("/Metadata")):
            del obj["/Metadata"]
            self.report.private_data += 1


def _is_javascript_action(action) -> bool:
    """Usado por `core/pdfa.py` (a conversão para PDF/A ainda faz a própria limpeza de
    JavaScript; a revisão dela é tratada à parte)."""
    return action is not None and action.get_object().get("/S") == "/JavaScript"


def _strip_annotation_javascript(annotation_ref) -> None:
    """Remove ações de JavaScript de `/A` e `/AA` de uma anotação (usado por `core/pdfa.py`)."""
    annotation = annotation_ref.get_object()

    action = annotation.get("/A")
    if _is_javascript_action(action):
        del annotation["/A"]

    additional_actions = annotation.get("/AA")
    if additional_actions is not None:
        aa = additional_actions.get_object()
        for trigger in list(aa.keys()):
            if _is_javascript_action(aa[trigger]):
                del aa[trigger]


def find_residual_risks(path: str, *, check_metadata: bool = True) -> list[str]:
    """Procura, num PDF já sanitizado, qualquer coisa que a sanitização deveria ter removido.
    Devolve a lista (vazia se estiver tudo limpo)."""
    reader = PdfReader(path)
    catalog = reader.trailer["/Root"]
    problems: set[str] = set()

    names = _resolve(catalog.get("/Names"))
    if isinstance(names, DictionaryObject):
        if "/JavaScript" in names:
            problems.add("JavaScript do documento")
        if "/EmbeddedFiles" in names:
            problems.add("anexos do documento")
    if "/AA" in catalog:
        problems.add("ações automáticas do documento")
    open_action = _resolve(catalog.get("/OpenAction"))
    if isinstance(open_action, DictionaryObject) and "/S" in open_action and _classify_action(open_action):
        problems.add("ação ao abrir o documento")
    acroform = _resolve(catalog.get("/AcroForm"))
    if isinstance(acroform, DictionaryObject) and "/XFA" in acroform:
        problems.add("formulário XFA")
    if check_metadata:
        info = reader.metadata or {}
        if any(info.get(key) for key in ("/Title", "/Author", "/Subject", "/Keywords", "/Creator")):
            problems.add("metadados do documento")
        if "/Metadata" in catalog:
            problems.add("metadados XMP do documento")

    stack = [reader.trailer.raw_get("/Root")]
    visited: set[int] = set()
    while stack:
        obj = _resolve(stack.pop())
        if id(obj) in visited:
            continue
        visited.add(id(obj))
        if isinstance(obj, DictionaryObject):
            action_type = obj.get("/S")
            subtype = obj.get("/Subtype")
            if subtype == "/FileAttachment":
                problems.add("anotação com arquivo anexado")
            if subtype in _RISKY_ANNOTATION_SUBTYPES:
                problems.add("anotação multimídia ou 3D")
            if action_type in _CODE_ACTION_TYPES or ("/S" in obj and "/JS" in obj):
                problems.add("JavaScript")
            elif action_type in _DANGEROUS_ACTION_TYPES:
                problems.add("ação que abre arquivos ou programas, ou envia dados")
            if action_type == "/URI" and _uri_risk(obj):
                problems.add("link com endereço perigoso (javascript:, file:, data:)")
            if _is_embedded_file_spec(obj) or obj.get("/Type") == "/EmbeddedFile":
                problems.add("arquivo embutido")
            if _is_page_or_form(obj) and "/PieceInfo" in obj:
                problems.add("dados privados de aplicativos")
            if check_metadata and obj is not catalog and "/Metadata" in obj and _is_xmp_stream(obj.raw_get("/Metadata")):
                problems.add("metadados XMP de páginas ou imagens")
            stack.extend(obj.values())
        elif isinstance(obj, ArrayObject):
            stack.extend(obj)
    return sorted(problems)


class SanitizeDocument(PDFOperation):
    """Remove metadados, JavaScript, ações perigosas, anexos e (opcionalmente) anotações de
    um PDF, e devolve um `SanitizeReport` com o que foi removido (ver o docstring do módulo)."""

    def run(
        self,
        input_path: str,
        output_path: str,
        remove_metadata: bool = True,
        remove_annotations: bool = False,
    ) -> SanitizeReport:
        reader = open_reader(input_path)
        report = SanitizeReport()
        sanitizer = _Sanitizer(report, remove_metadata)

        sanitizer.report_document_level(reader)  # o catálogo inteiro fica para trás
        pages = list(reader.pages)
        for page in pages:
            sanitizer.filter_annotations(page, remove_all=remove_annotations)
        sanitizer.walk(pages)

        writer = PdfWriter()  # sem clone_from: nada do catálogo original vem junto
        for page in pages:
            writer.add_page(page)

        if not remove_metadata:
            if reader.metadata:
                writer.add_metadata(reader.metadata)
            catalog = reader.trailer["/Root"]
            if "/Metadata" in catalog and _is_xmp_stream(catalog.raw_get("/Metadata")):
                writer.root_object[NameObject("/Metadata")] = catalog.raw_get("/Metadata").clone(writer)

        with atomic_output(output_path) as temp_path:
            with open(temp_path, "wb") as f:
                writer.write(f)
            problems = find_residual_risks(temp_path, check_metadata=remove_metadata)
            if problems:
                raise SanitizationVerificationError(
                    "A sanitização não conseguiu remover: " + "; ".join(problems) + ". O arquivo não foi salvo."
                )
        return report
