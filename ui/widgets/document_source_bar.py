"""O PDF de entrada das ferramentas: um cartão com o nome, as páginas e o tamanho do arquivo
aberto na aba, e "Trocar..." para abrir outro.

Substitui o antigo FilePicker(mode="open") nos painéis de ferramenta de entrada
única: como o visualizador central mostra sempre o mesmo documento, cada
ferramenta passa a atuar sobre esse arquivo em vez de pedir o seu próprio.
Sem documento, o cartão fica tracejado, com "Nenhum PDF escolhido" e "Abrir...".
"""

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.document_session import DocumentSession
from ui.i18n import PT_BR, get_language, tr
from ui.preferences import start_folder
from ui.viewer.viewer_icons import build_file_icon


def format_size(size: int) -> str:
    """"2,6 MB", "340 KB": o tamanho de um arquivo, curto."""
    if size >= 1024 * 1024:
        text = f"{size / 1024 / 1024:.1f} MB"
        return text.replace(".", ",") if get_language() == PT_BR else text
    return f"{max(1, round(size / 1024))} KB"


def _page_count(path: str) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(path).pages)
    except Exception:  # protegido, corrompido: o cartão mostra só o tamanho
        return None


class DocumentSourceBar(QFrame):
    def __init__(self, session: DocumentSession, parent=None):
        super().__init__(parent)
        self.setObjectName("InputChip")
        self.session = session
        self._display_name = tr("Nenhum PDF aberto")

        self.icon = QLabel()
        self.icon.setFixedSize(20, 20)
        self.icon.setPixmap(build_file_icon().pixmap(QSize(20, 20)))
        self.path_label = QLabel()
        self.path_label.setObjectName("documentSourceLabel")
        # QWidget.minimumSize() já é (0, 0) por padrão, então isso não é um no-op:
        # um QLabel sem minimumSize explícito usa minimumSizeHint() no layout, que
        # é o tamanho do texto completo (sem elisão) — o que impede o label de
        # encolher abaixo do nome completo do arquivo. Um mínimo pequeno e explícito
        # deixa o layout comprimi-lo livremente; o texto exibido é elidido à mão
        # em _update_elided_text() conforme o espaço realmente disponível.
        self.path_label.setMinimumWidth(40)
        self.meta_label = QLabel()
        self.meta_label.setProperty("ofRole", "secondary")

        self.open_button = QPushButton()
        self.open_button.setToolTip(tr("Abrir outro arquivo PDF"))
        self.open_button.clicked.connect(self._browse)

        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(self.path_label)
        texts.addWidget(self.meta_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(self.icon)
        layout.addLayout(texts, 1)
        layout.addWidget(self.open_button)

        session.path_changed.connect(self._refresh)
        session.history_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        # O nome do arquivo do usuário, não o da versão de trabalho; "*" se há alterações
        # não salvas.
        path = self.session.source_path()
        empty = not path
        name = Path(path).name if path else tr("Nenhum PDF escolhido")
        self._display_name = f"{name} *" if self.session.is_modified() else name
        self.path_label.setToolTip(path or self._display_name)
        self._update_elided_text()
        self.setProperty("empty", empty)
        self.style().unpolish(self)
        self.style().polish(self)
        self.open_button.setText(tr("Abrir...") if empty else tr("Trocar..."))
        self.open_button.setProperty("ofVariant", "" if empty else "ghost")
        self.open_button.style().unpolish(self.open_button)
        self.open_button.style().polish(self.open_button)
        self.meta_label.setText(self._meta(self.session.path()) if not empty else "")
        self.meta_label.setVisible(not empty)

    def _meta(self, working_path: str | None) -> str:
        """"25 páginas · 2,6 MB", da versão de trabalho (a que a ferramenta vai ler)."""
        if not working_path or not os.path.exists(working_path):
            return ""
        parts = [format_size(os.path.getsize(working_path))]
        pages = _page_count(working_path)
        if pages is not None:
            parts.insert(0, tr("{count} página(s)").format(count=pages))
        return " · ".join(parts)

    def _update_elided_text(self):
        metrics = self.path_label.fontMetrics()
        available_width = max(self.path_label.width(), 1)
        elided = metrics.elidedText(self._display_name, Qt.TextElideMode.ElideMiddle, available_width)
        self.path_label.setText(elided)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar arquivo"), start_folder(), "PDF (*.pdf)")
        if path:
            self.session.open(path)

    def path(self) -> str:
        return self.session.path() or ""
