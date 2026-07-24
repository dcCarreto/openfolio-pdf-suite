"""Indica o PDF atualmente aberto na sessão compartilhada e permite trocá-lo.

Substitui o antigo FilePicker(mode="open") nos painéis de ferramenta de entrada
única: como o visualizador central mostra sempre o mesmo documento, cada
ferramenta passa a atuar sobre esse arquivo em vez de pedir o seu próprio.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from ui.document_session import DocumentSession
from ui.i18n import tr


class DocumentSourceBar(QWidget):
    def __init__(self, session: DocumentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._display_name = tr("Nenhum PDF aberto")

        self.path_label = QLabel()
        self.path_label.setObjectName("documentSourceLabel")
        # QWidget.minimumSize() já é (0, 0) por padrão, então isso não é um no-op:
        # um QLabel sem minimumSize explícito usa minimumSizeHint() no layout, que
        # é o tamanho do texto completo (sem elisão) — o que impede o label de
        # encolher abaixo do nome completo do arquivo. Um mínimo pequeno e explícito
        # deixa o layout comprimi-lo livremente; o texto exibido é elidido à mão
        # em _update_elided_text() conforme o espaço realmente disponível.
        self.path_label.setMinimumWidth(40)

        open_button = QPushButton(tr("Abrir..."))
        open_button.setToolTip(tr("Abrir outro arquivo PDF"))
        open_button.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.path_label, 1)
        layout.addWidget(open_button)

        session.path_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        path = self.session.path()
        self._display_name = Path(path).name if path else tr("Nenhum PDF aberto")
        self.path_label.setToolTip(self._display_name)
        self._update_elided_text()

    def _update_elided_text(self):
        metrics = self.path_label.fontMetrics()
        available_width = max(self.path_label.width(), 1)
        elided = metrics.elidedText(self._display_name, Qt.TextElideMode.ElideMiddle, available_width)
        self.path_label.setText(elided)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar arquivo"), "", "PDF (*.pdf)")
        if path:
            self.session.open(path)

    def path(self) -> str:
        return self.session.path() or ""
