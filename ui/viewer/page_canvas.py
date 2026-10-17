"""QLabel que expõe eventos de mouse como sinais, para a ferramenta de anotações
desenhar diretamente sobre a página renderizada (modo página única)."""

from PySide6.QtCore import QPointF, Signal
from PySide6.QtWidgets import QLabel


class PageCanvas(QLabel):
    """As posições dos sinais são relativas à página desenhada, não ao rótulo: o
    `QScrollArea` estica o rótulo até a área visível e a página fica centralizada nele,
    então com a página menor que a tela (zoom baixo) o canto do rótulo não é o canto da
    página — e antes os cliques e arrastos caíam deslocados."""

    mouse_pressed = Signal(float, float)
    mouse_moved = Signal(float, float)
    mouse_released = Signal(float, float)

    def pixmap_offset(self) -> QPointF:
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return QPointF(0, 0)
        size = pixmap.deviceIndependentSize()
        return QPointF(max(0.0, (self.width() - size.width()) / 2), max(0.0, (self.height() - size.height()) / 2))

    def _page_position(self, event) -> QPointF:
        return event.position() - self.pixmap_offset()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        pos = self._page_position(event)
        self.mouse_pressed.emit(pos.x(), pos.y())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        pos = self._page_position(event)
        self.mouse_moved.emit(pos.x(), pos.y())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        pos = self._page_position(event)
        self.mouse_released.emit(pos.x(), pos.y())
