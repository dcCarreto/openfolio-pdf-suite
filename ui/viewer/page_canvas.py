"""QLabel que expõe eventos de mouse como sinais, para a ferramenta de anotações
desenhar diretamente sobre a página renderizada (modo página única)."""

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtWidgets import QLabel


class PageCanvas(QLabel):
    """As posições dos sinais são relativas à página desenhada, não ao rótulo: o
    `QScrollArea` estica o rótulo até a área visível e a página fica centralizada nele,
    então com a página menor que a tela (zoom baixo) o canto do rótulo não é o canto da
    página — e antes os cliques e arrastos caíam deslocados."""

    mouse_pressed = Signal(float, float)
    mouse_moved = Signal(float, float)  # com um botão apertado (arrastos)
    mouse_released = Signal(float, float)
    mouse_hovered = Signal(float, float)  # sem botão: o mouse só passa (o cursor nos links)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.pressed_button = Qt.MouseButton.NoButton  # o do último clique

    def pixmap_offset(self) -> QPointF:
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return QPointF(0, 0)
        size = pixmap.deviceIndependentSize()
        area = self.contentsRect()  # a margem de cima, com a barra de marcação aberta
        return QPointF(
            area.x() + max(0.0, (area.width() - size.width()) / 2),
            area.y() + max(0.0, (area.height() - size.height()) / 2),
        )

    def _page_position(self, event) -> QPointF:
        return event.position() - self.pixmap_offset()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.pressed_button = event.button()
        pos = self._page_position(event)
        self.mouse_pressed.emit(pos.x(), pos.y())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        pos = self._page_position(event)
        if event.buttons() == Qt.MouseButton.NoButton:
            self.mouse_hovered.emit(pos.x(), pos.y())
        else:
            self.mouse_moved.emit(pos.x(), pos.y())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        pos = self._page_position(event)
        self.mouse_released.emit(pos.x(), pos.y())
