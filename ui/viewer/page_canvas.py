"""QLabel que expõe eventos de mouse como sinais, para a ferramenta de anotações
desenhar diretamente sobre a página renderizada (modo página única)."""

import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QLabel


class PageCanvas(QLabel):
    """As posições dos sinais são relativas à página desenhada, não ao rótulo: o
    `QScrollArea` estica o rótulo até a área visível e a página fica centralizada nele,
    então com a página menor que a tela (zoom baixo) o canto do rótulo não é o canto da
    página — e antes os cliques e arrastos caíam deslocados.

    Só o botão esquerdo vira sinal; os outros (menu, arrastar a página, voltar) seguem para o
    visualizador, que os recebe na área de rolagem."""

    mouse_pressed = Signal(float, float)
    mouse_moved = Signal(float, float)  # com o botão apertado (arrastos)
    mouse_released = Signal(float, float)
    mouse_hovered = Signal(float, float)  # sem botão: o mouse só passa (o cursor nos links)
    mouse_double_clicked = Signal(float, float)
    mouse_triple_clicked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.pressed_button = Qt.MouseButton.NoButton  # o do último clique
        self.pressed_modifiers = Qt.KeyboardModifier.NoModifier  # Shift + clique estende a seleção
        self._selection_rects: list[QRectF] = []
        self._selection_color = QColor()
        self._double_click_at = 0.0

    def set_selection(self, rects: list[QRectF], color: QColor) -> None:
        """O texto selecionado, por cima da imagem: mudar a seleção não redesenha a página."""
        if rects or self._selection_rects:
            self._selection_rects, self._selection_color = rects, color
            self.update()

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

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._selection_rects:
            painter = QPainter(self)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._selection_color)
            painter.translate(self.pixmap_offset())
            for rect in self._selection_rects:
                painter.drawRect(rect)
            painter.end()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.pressed_button = event.button()
        self.pressed_modifiers = event.modifiers()
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._page_position(event)
        # O terceiro clique seguido: o Qt só conhece o duplo.
        if time.monotonic() - self._double_click_at < QApplication.doubleClickInterval() / 1000:
            self._double_click_at = 0.0
            self.mouse_triple_clicked.emit(pos.x(), pos.y())
            return
        self.mouse_pressed.emit(pos.x(), pos.y())

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        self.pressed_button = event.button()
        self._double_click_at = time.monotonic()
        pos = self._page_position(event)
        self.mouse_double_clicked.emit(pos.x(), pos.y())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        pos = self._page_position(event)
        if event.buttons() == Qt.MouseButton.NoButton:
            self.mouse_hovered.emit(pos.x(), pos.y())
        elif event.buttons() & Qt.MouseButton.LeftButton:
            self.mouse_moved.emit(pos.x(), pos.y())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self._page_position(event)
            self.mouse_released.emit(pos.x(), pos.y())
