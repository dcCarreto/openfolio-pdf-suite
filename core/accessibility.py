"""Verificação (e pequenos ajustes seguros) de acessibilidade de PDFs, na linha do
checador de acessibilidade do Acrobat — mas um subconjunto dele, não uma reimplementação.

PDF/UA de verdade exige uma árvore de estrutura (`/StructTreeRoot`) com conteúdo marcado
(`BDC`/`EMC` no content stream, ligado a cada elemento da árvore por MCID) — ordem de
leitura, tabelas com cabeçalho, texto alternativo em figura, tudo depende dessa estrutura
existir e estar correta. Gerar essa estrutura do zero de forma automática ("tagueamento
automático") exigiria reescrever o content stream de cada página inserindo os marcadores
certos nos lugares certos — o mesmo tipo de cirurgia arriscada que este projeto já evitou
em `core/edit_text.py` e no comentário de `core/redaction.py`. Pior: se a tag ficar
malformada, um leitor de tela pode ignorá-la silenciosamente ou ler a página fora de ordem,
e o arquivo ainda ficaria marcado como "Marked = true" — uma falsa promessa de
acessibilidade pior do que não ter tag nenhuma. Por isso esta ferramenta não tenta gerar
estrutura: verifica o que dá pra verificar com segurança (idioma declarado, título,
presença de árvore de estrutura, texto alternativo nas figuras já tagueadas) e só ajusta
automaticamente o que é sempre seguro de ajustar — idioma e título do documento, os únicos
dois itens do checador do Acrobat que são simples metadados sem risco de corromper conteúdo.
"""

from dataclasses import dataclass, field

from pypdf import PdfWriter
from pypdf.generic import BooleanObject, DictionaryObject, NameObject, TextStringObject

from .base import READ, PDFOperation, open_reader, write_pdf
from .messages import Message


@dataclass
class AccessibilityReport:
    is_compliant: bool
    issues: list[str] = field(default_factory=list)


def _resolve(value):
    return value.get_object() if hasattr(value, "get_object") else value


def _walk_struct_elements(node, visited: set[int] | None = None):
    """Percorre a árvore de estrutura (se houver) e produz cada elemento `/StructElem`.

    `/K` pode ser um elemento, um array ou uma referência indireta para qualquer um dos
    dois (antes, um array indireto não era percorrido e as figuras dentro dele não eram
    verificadas). Ciclos são ignorados."""
    visited = visited if visited is not None else set()
    if id(node) in visited:
        return
    visited.add(id(node))
    kids = _resolve(node.get("/K"))
    if kids is None:
        return
    if not isinstance(kids, list):
        kids = [kids]
    for kid in kids:
        kid_obj = _resolve(kid)
        if isinstance(kid_obj, DictionaryObject) and "/S" in kid_obj:
            yield kid_obj
            yield from _walk_struct_elements(kid_obj, visited)


def _standard_role(role, role_map: dict) -> str:
    """O tipo padrão de uma tag, seguindo o `/RoleMap` (tags próprias mapeadas para tipos
    padrão, como "/Imagem" -> "/Figure")."""
    seen = set()
    while role in role_map and role not in seen:
        seen.add(role)
        role = role_map[role]
    return role


def _fields(acroform):
    stack = list(_resolve(acroform.get("/Fields")) or [])
    seen: set[int] = set()
    while stack:
        field_obj = _resolve(stack.pop())
        if not isinstance(field_obj, DictionaryObject) or id(field_obj) in seen:
            continue
        seen.add(id(field_obj))
        kids = [_resolve(kid) for kid in _resolve(field_obj.get("/Kids")) or []]
        named_kids = [kid for kid in kids if isinstance(kid, DictionaryObject) and "/T" in kid]
        if named_kids:
            stack.extend(named_kids)  # nó intermediário de nomes hierárquicos
        else:
            yield field_obj


class CheckAccessibility(PDFOperation):
    """Verifica um subconjunto dos requisitos de acessibilidade (PDF/UA): idioma
    declarado, título do documento (e exibido na barra de título), árvore de estrutura
    presente, texto alternativo em toda figura tagueada (inclusive tags próprias mapeadas
    para Figure no `/RoleMap`), ordem de tabulação pela estrutura nas páginas com
    anotações, e descrição (`/TU`) nos campos de formulário. Não é validação PDF/UA
    completa — não verifica ordem de leitura, cabeçalho de tabela nem contraste de cor."""

    def run(self, input_path: str) -> AccessibilityReport:
        reader = open_reader(input_path, purpose=READ)
        issues: list[str] = []
        catalog = reader.trailer["/Root"]

        if not catalog.get("/Lang"):
            issues.append("O documento não declara um idioma (/Lang).")

        title = (reader.metadata or {}).get("/Title")
        if not title:
            issues.append("O documento não tem um título nos metadados.")
        viewer_prefs = _resolve(catalog.get("/ViewerPreferences"))
        if not (isinstance(viewer_prefs, DictionaryObject) and viewer_prefs.get("/DisplayDocTitle")):
            issues.append("O leitor mostra o nome do arquivo em vez do título (falta /DisplayDocTitle).")

        mark_info = catalog.get("/MarkInfo")
        is_marked = bool(mark_info and mark_info.get_object().get("/Marked"))
        struct_root = catalog.get("/StructTreeRoot")
        if not is_marked or struct_root is None:
            issues.append("O documento não tem uma árvore de estrutura (não está tagueado).")
        else:
            root = struct_root.get_object()
            role_map = {
                key: value for key, value in (_resolve(root.get("/RoleMap")) or {}).items()
            }
            figures_without_alt = 0
            for element in _walk_struct_elements(root):
                if _standard_role(element.get("/S"), role_map) == "/Figure" and not element.get("/Alt"):
                    figures_without_alt += 1
            if figures_without_alt:
                issues.append(
                    Message(
                        "{count} figura(s) tagueada(s) sem texto alternativo (/Alt).",
                        count=figures_without_alt,
                    )
                )

        pages_without_tab_order = [
            index + 1
            for index, page in enumerate(reader.pages)
            if page.get("/Annots") and page.get("/Tabs") != "/S"
        ]
        if pages_without_tab_order:
            issues.append(
                Message(
                    "{count} página(s) com links ou campos sem ordem de tabulação pela estrutura (/Tabs /S).",
                    count=len(pages_without_tab_order),
                )
            )

        acroform = _resolve(catalog.get("/AcroForm"))
        if isinstance(acroform, DictionaryObject):
            unlabeled = sorted(
                str(field_obj.get("/T", "?")) for field_obj in _fields(acroform) if not field_obj.get("/TU")
            )
            if unlabeled:
                issues.append(
                    Message(
                        "{count} campo(s) de formulário sem descrição para leitores de tela (/TU): {names}.",
                        count=len(unlabeled),
                        names=", ".join(unlabeled[:8]),
                    )
                )

        return AccessibilityReport(is_compliant=not issues, issues=issues)


class FixBasicAccessibilityIssues(PDFOperation):
    """Ajusta os itens do checador de acessibilidade que são simples metadados ou
    preferências, sem qualquer risco de corromper conteúdo: idioma e título do documento,
    `/ViewerPreferences/DisplayDocTitle` (para o título aparecer na barra de título do
    leitor) e a ordem de tabulação pela estrutura (`/Tabs /S`) nas páginas com anotações.
    Não tagueia o documento — ver o docstring do módulo para o porquê."""

    def run(self, input_path: str, output_path: str, language: str, title: str) -> None:
        if not language:
            raise ValueError("Informe um idioma (ex.: pt-BR).")
        if not title:
            raise ValueError("Informe um título para o documento.")

        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)

        writer.root_object[NameObject("/Lang")] = TextStringObject(language)

        existing_metadata = reader.metadata or {}
        writer.add_metadata(
            {
                "/Title": title,
                "/Author": existing_metadata.get("/Author", "") or "",
                "/Subject": existing_metadata.get("/Subject", "") or "",
                "/Keywords": existing_metadata.get("/Keywords", "") or "",
            }
        )

        viewer_prefs = writer.root_object.get("/ViewerPreferences")
        if viewer_prefs is None:
            viewer_prefs = DictionaryObject()
            writer.root_object[NameObject("/ViewerPreferences")] = viewer_prefs
        else:
            viewer_prefs = viewer_prefs.get_object()
        viewer_prefs[NameObject("/DisplayDocTitle")] = BooleanObject(True)

        for page in writer.pages:
            if page.get("/Annots"):
                page[NameObject("/Tabs")] = NameObject("/S")

        write_pdf(writer, output_path)
