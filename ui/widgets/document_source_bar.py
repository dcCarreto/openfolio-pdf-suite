"""O PDF de entrada das ferramentas: um cartão com o nome, as páginas e o tamanho do arquivo
aberto na aba, e "Trocar..." para abrir outro.

Substitui o antigo FilePicker(mode="open") nos painéis de ferramenta de entrada
única: como o visualizador central mostra sempre o mesmo documento, cada
ferramenta passa a atuar sobre esse arquivo em vez de pedir o seu próprio.
Sem documento, o cartão fica tracejado, com "Nenhum PDF aberto", uma linha de ajuda e
"Abrir PDF...". O estado (não salvo) fica no selo da barra do visualizador, não no nome.
Compacto (Anotações, onde a lista de comentários precisa do espaço), o arquivo cabe numa linha
só: "Contrato.pdf · 25 págs.".
"""

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.document_session import DocumentSession
from ui.i18n import PT_BR, get_language, plural, tr
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
    def __init__(
        self,
        session: DocumentSession,
        parent=None,
        empty_hint: str = "Abra ou arraste o PDF que quer usar.",
        compact: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("InputChip")
        self.setProperty("compact", compact)
        self.session = session
        self._compact = compact
        self._display_name = tr("Nenhum PDF aberto")
        self._empty_hint = empty_hint

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
        self.meta_label.setProperty("ofRole", "help")
        self.meta_label.setWordWrap(True)

        self.open_button = QPushButton()
        self.open_button.setToolTip(tr("Abrir outro arquivo PDF"))
        self.open_button.clicked.connect(self._browse)

        texts = QHBoxLayout() if compact else QVBoxLayout()
        texts.setSpacing(6 if compact else 2)
        texts.addWidget(self.path_label)
        texts.addWidget(self.meta_label)
        if compact:
            texts.addStretch(1)
        if compact:
            self.meta_label.setWordWrap(False)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(*((12, 4, 4, 4) if compact else (12, 10, 8, 10)))
        self._layout.setSpacing(10)
        self._layout.addWidget(self.icon)
        self._layout.addLayout(texts, 1)
        self._layout.addWidget(self.open_button)

        session.path_changed.connect(self._refresh)
        session.history_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        # O nome do arquivo do usuário, não o da versão de trabalho.
        path = self.session.source_path()
        empty = not path
        self._display_name = Path(path).name if path else tr("Nenhum PDF aberto")
        self.path_label.setToolTip(path or "")
        self._update_elided_text()
        self.setProperty("empty", empty)
        self.style().unpolish(self)
        self.style().polish(self)
        self.icon.setVisible(not empty)
        self.open_button.setText(tr("Abrir PDF...") if empty else tr("Trocar..."))
        self.open_button.setProperty("ofVariant", "" if empty else "ghost")
        self.open_button.style().unpolish(self.open_button)
        self.open_button.style().polish(self.open_button)
        self.meta_label.setText(tr(self._empty_hint) if empty else self._meta(self.session.path()))
        self.meta_label.setVisible(not (self._compact and empty))

    def _meta(self, working_path: str | None) -> str:
        """"25 páginas · 2,6 MB", da versão de trabalho (a que a ferramenta vai ler)."""
        if not working_path or not os.path.exists(working_path):
            return ""
        pages = _page_count(working_path)
        if self._compact:  # "· 25 págs.", logo depois do nome
            return f"· {plural(pages, '1 pág.', '{count} págs.')}" if pages is not None else ""
        parts = [format_size(os.path.getsize(working_path))]
        if pages is not None:
            parts.insert(0, plural(pages, "1 página", "{count} páginas"))
        return " · ".join(parts)

    def _update_elided_text(self):
        metrics = self.path_label.fontMetrics()
        available_width = max(self.path_label.width(), 1)
        if self._compact and self.meta_label.isVisibleTo(self):
            # O nome ocupa o que sobra do cartão; "· 25 págs." vem logo depois dele.
            margins = self._layout.contentsMargins()
            others = self.icon.width() + self.open_button.sizeHint().width() + self.meta_label.sizeHint().width()
            spacing = self._layout.spacing() * 2 + 6
            available_width = max(1, self.width() - margins.left() - margins.right() - others - spacing)
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
