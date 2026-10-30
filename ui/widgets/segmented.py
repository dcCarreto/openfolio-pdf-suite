"""Controle segmentado: um container com borda e um segmento marcado por vez. As setas trocam de
segmento e o foco fica no marcado; Tab entra e sai dele como um controle só."""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget


class Segmented(QWidget):
    chosen = Signal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self.buttons: list[QToolButton] = []
        for index, label in enumerate(labels):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus if index == 0 else Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _checked=False, i=index: self._choose(i))
            button.installEventFilter(self)  # as setas chegam ao botão com o foco
            self._group.addButton(button)
            layout.addWidget(button, 1)
            self.buttons.append(button)

    def current(self) -> int:
        return next((i for i, button in enumerate(self.buttons) if button.isChecked()), -1)

    def set_current(self, index: int) -> None:
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus if i == index else Qt.FocusPolicy.NoFocus)

    def _choose(self, index: int) -> None:
        self.set_current(index)
        self.chosen.emit(index)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(event.key())
            if step is not None:
                target = (self.current() + step) % len(self.buttons)
                self._choose(target)
                self.buttons[target].setFocus()
                return True
        return super().eventFilter(watched, event)
