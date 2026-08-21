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

from .base import PDFOperation, open_reader


@dataclass
class AccessibilityReport:
    is_compliant: bool
    issues: list[str] = field(default_factory=list)


def _walk_struct_elements(node):
    """Percorre a árvore de estrutura (se houver) e produz cada elemento `/StructElem`."""
    kids = node.get("/K")
    if kids is None:
        return
    if not isinstance(kids, list):
        kids = [kids]
    for kid in kids:
        kid_obj = kid.get_object() if hasattr(kid, "get_object") else kid
        if isinstance(kid_obj, DictionaryObject) and "/S" in kid_obj:
            yield kid_obj
            yield from _walk_struct_elements(kid_obj)


class CheckAccessibility(PDFOperation):
    """Verifica um subconjunto dos requisitos de acessibilidade (PDF/UA): idioma
    declarado, título do documento, árvore de estrutura presente, e texto alternativo em
    toda figura tagueada. Não é validação PDF/UA completa — não verifica ordem de leitura,
    cabeçalho de tabela, rótulo de campo de formulário nem contraste de cor."""

    def run(self, input_path: str) -> AccessibilityReport:
        reader = open_reader(input_path)
        issues: list[str] = []
        catalog = reader.trailer["/Root"]

        if not catalog.get("/Lang"):
            issues.append("O documento não declara um idioma (/Lang).")

        title = (reader.metadata or {}).get("/Title")
        if not title:
            issues.append("O documento não tem um título nos metadados.")

        mark_info = catalog.get("/MarkInfo")
        is_marked = bool(mark_info and mark_info.get_object().get("/Marked"))
        struct_root = catalog.get("/StructTreeRoot")
        if not is_marked or struct_root is None:
            issues.append("O documento não tem uma árvore de estrutura (não está tagueado).")
        else:
            figures_without_alt = 0
            for element in _walk_struct_elements(struct_root.get_object()):
                if element.get("/S") == "/Figure" and not element.get("/Alt"):
                    figures_without_alt += 1
            if figures_without_alt:
                issues.append(
                    f"{figures_without_alt} figura(s) tagueada(s) sem texto alternativo (/Alt)."
                )

        return AccessibilityReport(is_compliant=not issues, issues=issues)


class FixBasicAccessibilityIssues(PDFOperation):
    """Ajusta os únicos dois itens do checador de acessibilidade que são simples
    metadados, sem qualquer risco de corromper conteúdo: idioma e título do documento
    (e `/ViewerPreferences/DisplayDocTitle`, para o título aparecer na barra de título do
    leitor). Não tagueia o documento — ver o docstring do módulo para o porquê."""

    def run(self, input_path: str, output_path: str, language: str, title: str) -> None:
        if not language:
            raise ValueError("Informe um idioma (ex.: pt-BR).")
        if not title:
            raise ValueError("Informe um título para o documento.")

        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=input_path)

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

        with open(output_path, "wb") as f:
            writer.write(f)
