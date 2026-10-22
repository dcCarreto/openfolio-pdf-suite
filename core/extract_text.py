"""Extração de texto de arquivos PDF."""

from .base import EXTRACT, atomic_output, open_reader


def page_text(page, layout: bool = False) -> str:
    """O texto da página; com `layout`, na posição em que aparece (colunas alinhadas)."""
    if not layout:
        return page.extract_text()
    if "/Contents" not in page:  # o modo layout do pypdf quebra em página sem conteúdo
        return ""
    return page.extract_text(extraction_mode="layout")


class ExtractText:
    """Extrai todo o texto de um PDF para um arquivo .txt; com `layout`, cada linha mantém
    a posição do texto na página (colunas e tabelas continuam alinhadas)."""

    def run(self, input_path: str, output_path: str, layout: bool = False) -> None:
        reader = open_reader(input_path, purpose=EXTRACT)
        text = "\n\n".join(page_text(page, layout) for page in reader.pages)

        with atomic_output(output_path) as temp_path:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(text)
