"""QLabel que expõe eventos de mouse como sinais, para a ferramenta de anotações
desenhar diretamente sobre a página renderizada (modo página única)."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel


class PageCanvas(QLabel):
    mouse_pressed = Signal(float, float)
    mouse_moved = Signal(float, float)
    mouse_released = Signal(float, float)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        pos = event.position()
        self.mouse_pressed.emit(pos.x(), pos.y())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        pos = event.position()
        self.mouse_moved.emit(pos.x(), pos.y())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        pos = event.position()
        self.mouse_released.emit(pos.x(), pos.y())
