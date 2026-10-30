"""Modo apresentação (A15): o documento em tela cheia, uma página por vez, ajustada à tela.

Avança com →, ↓, PgDn, espaço, Enter ou clique; volta com ←, ↑, PgUp, Backspace ou clique
com o botão direito; Home e End vão à primeira e à última; Esc sai. A roda do mouse também
passa as páginas. Um clique num link o segue, e o cursor, escondido, só aparece sobre um
link. O PDF é lido para a memória, como na comparação: a janela não prende o
arquivo da versão de trabalho.
"""

from pathlib import Path

import pypdfium2 as pdfium
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent, QPalette
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.base import known_password
from core.geometry import PageGeometry
from core.page_links import PageLink, page_links
from core.progress import PDFIUM_LOCK
from ui.i18n import tr
from ui.viewer.render import render_page

_NEXT_KEYS = {Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_N}
_PREV_KEYS = {Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace, Qt.Key.Key_P}


class PresentationWindow(QWidget):
    finished = Signal(int)  # a página em que a apresentação parou, para o visualizador ir até ela

    def __init__(self, path: str, page: int = 0, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(tr("Apresentação"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.black)
        self.setPalette(palette)
        self.setStyleSheet("background-color: black;")

        self._document = pdfium.PdfDocument(Path(path).read_bytes(), password=known_password(path))
        self._path = path
        self._page = max(0, min(len(self._document) - 1, page))
        self._scale = 1.0
        self._links: dict[int, list[PageLink]] = {}
        self._geometries: dict[int, PageGeometry] = {}

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMouseTracking(True)
        self.setMouseTracking(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

    def page(self) -> int:
        return self._page

    def page_count(self) -> int:
        return len(self._document)

    def go_to(self, page: int) -> None:
        page = max(0, min(self.page_count() - 1, page))
        if page != self._page or self.label.pixmap().isNull():
            self._page = page
            self._render()

    def _render(self) -> None:
        if not self.width() or not self.height():
            return
        with PDFIUM_LOCK:
            pdf_page = self._document[self._page]
            width, height = pdf_page.get_size()  # já como a página aparece (com a /Rotate)
            scale = min(self.width() / width, self.height() / height) if width and height else 1.0
            pixmap = render_page(pdf_page, scale, self.devicePixelRatioF())
            pdf_page.close()
        self._scale = scale
        self.label.setPixmap(pixmap)

    # -- links ------------------------------------------------------------------

    def _page_links(self) -> list[PageLink]:
        links = self._links.get(self._page)
        if links is None:
            try:
                with PDFIUM_LOCK:
                    pdf_page = self._document[self._page]
                    try:
                        links = page_links(self._document, pdf_page, self._path, self._page)
                        self._geometries[self._page] = PageGeometry.from_pdfium_page(pdf_page)
                    finally:
                        pdf_page.close()
            except Exception:
                links = []  # um link malformado não atrapalha a apresentação
            self._links[self._page] = links
        return links

    def link_at(self, position) -> PageLink | None:
        """O link sob um ponto da janela. Um link para outro PDF fica de fora: abrir outro
        documento não cabe no meio de uma apresentação."""
        pixmap = self.label.pixmap()
        links = self._page_links()
        if pixmap.isNull() or not links:
            return None
        size = pixmap.deviceIndependentSize()
        x = position.x() - (self.width() - size.width()) / 2
        y = position.y() - (self.height() - size.height()) / 2
        point = self._geometries[self._page].screen_to_user(x, y, self._scale)
        return next((link for link in links if not link.file and link.contains(*point)), None)

    def _follow_link(self, link: PageLink) -> None:
        if link.url:
            QDesktopServices.openUrl(QUrl(link.url))
        elif link.target_page is not None:
            self.go_to(link.target_page)
        elif link.named == "NextPage":
            self.go_to(self._page + 1)
        elif link.named == "PrevPage":
            self.go_to(self._page - 1)
        elif link.named == "FirstPage":
            self.go_to(0)
        elif link.named == "LastPage":
            self.go_to(self.page_count() - 1)

    # -- eventos ----------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in _NEXT_KEYS:
            self.go_to(self._page + 1)
        elif key in _PREV_KEYS:
            self.go_to(self._page - 1)
        elif key == Qt.Key.Key_Home:
            self.go_to(0)
        elif key == Qt.Key.Key_End:
            self.go_to(self.page_count() - 1)
        elif key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        over_link = self.link_at(event.position()) is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if over_link else Qt.CursorShape.BlankCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            link = self.link_at(event.position())
            if link is not None:
                self._follow_link(link)
            else:
                self.go_to(self._page + 1)
        elif event.button() == Qt.MouseButton.RightButton:
            self.go_to(self._page - 1)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.go_to(self._page + (1 if delta < 0 else -1))

    def closeEvent(self, event):
        with PDFIUM_LOCK:
            self._document.close()
        self.finished.emit(self._page)
        super().closeEvent(event)
