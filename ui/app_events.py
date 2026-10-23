"""Arquivos que chegam ao app de fora: linha de comando, "Abrir com" e arrastar e soltar.

Antes o app ignorava `sys.argv`: o `.desktop` declarava `%U`, mas abrir um PDF pelo
explorador de arquivos só abria a janela vazia.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, QObject


def pdf_paths_from_arguments(arguments: list[str]) -> list[str]:
    """Os PDFs que existem entre os argumentos (ignora opções e arquivos que não são PDF)."""
    paths = []
    for argument in arguments:
        if argument.startswith("-"):
            continue
        if argument.startswith("file://"):
            from PySide6.QtCore import QUrl

            argument = QUrl(argument).toLocalFile()
        path = Path(argument)
        if path.suffix.lower() == ".pdf" and path.is_file():
            paths.append(str(path.resolve()))
    return paths


def pdf_paths_from_mime(mime_data) -> list[str]:
    """Os PDFs locais de um arrastar e soltar."""
    if mime_data is None or not mime_data.hasUrls():
        return []
    return pdf_paths_from_arguments([url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()])


class FileOpenFilter(QObject):
    """Recebe o evento FileOpen do macOS (duplo clique ou "Abrir com" no Finder)."""

    def __init__(self, open_path, parent=None):
        super().__init__(parent)
        self._open_path = open_path

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path and path.lower().endswith(".pdf"):
                self._open_path(path)
                return True
        return super().eventFilter(watched, event)
