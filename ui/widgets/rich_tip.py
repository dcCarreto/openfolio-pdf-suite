"""Dica rica (seção 7): o nome em 600 com a tecla à direita e uma frase sobre o efeito, num
cartão flutuante de 240 px. Abre 500 ms depois que o mouse para em cima ou na hora, com o foco
do teclado. Substitui a dica simples do Qt na coluna rápida, nas ferramentas e na barra de
marcação.

O texto também fica em `toolTip()` (em HTML, como antes) e na descrição para o leitor de tela;
só a janelinha do Qt deixa de aparecer.
"""

import html

import shiboken6
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import theme

DELAY_MS = 500
WIDTH = 240
GAP = 8  # do controle até o cartão

_KEYBOARD = (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.OtherFocusReason)
_CLOSING = (
    QEvent.Type.Leave,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.Wheel,
    QEvent.Type.KeyPress,
    QEvent.Type.FocusOut,
    QEvent.Type.Hide,
    QEvent.Type.EnabledChange,
)


class RichTip(QFrame):
    """O cartão, um por janela, por cima de tudo dela (como a gaveta e os popovers)."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.setObjectName("RichTip")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(WIDTH)
        self.title = QLabel()
        self.title.setObjectName("RichTipTitle")
        self.title.setWordWrap(True)
        self.key = QLabel()
        self.key.setObjectName("Kbd")
        self.body = QLabel()
        self.body.setObjectName("RichTipBody")
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setWordWrap(True)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.title, 1)
        head.addWidget(self.key, 0, Qt.AlignmentFlag.AlignTop)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addLayout(head)
        layout.addWidget(self.body)
        self.hide()

    def show_for(self, widget: QWidget) -> None:
        self.title.setText(widget.property("ofTipTitle") or "")
        key = widget.property("ofTipKey") or ""
        self.key.setText(key)
        self.key.setVisible(bool(key))
        body = widget.property("ofTipBody") or ""
        self.body.setText(body)
        self.body.setVisible(bool(body))
        self.setGraphicsEffect(theme.floating_shadow(self))  # na cor do tema de agora
        layout = self.layout()
        assert layout is not None
        layout.activate()
        # A altura com as linhas quebradas nos 240 px (adjustSize não sabe da quebra).
        self.resize(WIDTH, layout.totalHeightForWidth(WIDTH))
        self.move(self._place(widget))
        self.raise_()
        self.show()

    def _place(self, widget: QWidget) -> QPoint:
        """Ao lado pedido do controle, ou do outro lado se não couber; sempre dentro da janela."""
        window = self.parentWidget()
        assert window is not None
        anchor = QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())
        width, height = self.width(), self.height()
        side = widget.property("ofTipSide") or "right"
        if side == "below":
            x, y = anchor.left(), anchor.bottom() + 1 + GAP
            if y + height > window.height():
                y = anchor.top() - GAP - height
        else:
            right = anchor.right() + 1 + GAP
            left = anchor.left() - GAP - width
            fits_right = right + width <= window.width()
            x = left if (side == "left" and left >= 0) or not fits_right else right
            y = anchor.top()
        x = max(GAP, min(x, window.width() - width - GAP))
        y = max(GAP, min(y, window.height() - height - GAP))
        return QPoint(x, y)


class _Tips(QObject):
    """Um filtro para todos os controles com dica rica: o atraso, o foco e o que a fecha."""

    def __init__(self):
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DELAY_MS)
        self._timer.timeout.connect(self._show_waiting)
        self._waiting: QWidget | None = None
        self._shown: RichTip | None = None

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            return True  # a dica simples do Qt não aparece por cima da rica
        if kind == QEvent.Type.Enter:
            self._waiting = watched
            self._timer.start()
        elif kind == QEvent.Type.FocusIn and event.reason() in _KEYBOARD:
            self.show(watched)
        elif kind in _CLOSING:
            self.hide()
        return False

    def _show_waiting(self) -> None:
        widget = self._waiting  # o Leave, um clique ou uma tecla antes dos 500 ms já o tiraram
        if widget is not None and shiboken6.isValid(widget) and widget.isVisible():
            self.show(widget)

    def show(self, widget: QWidget) -> None:
        self._timer.stop()
        if not widget.isEnabled() or not widget.property("ofTipTitle"):
            return
        window = widget.window()
        tip = window.findChild(RichTip, options=Qt.FindChildOption.FindDirectChildrenOnly)
        if tip is None:
            tip = RichTip(window)
        self.hide()
        tip.show_for(widget)
        self._shown = tip

    def hide(self) -> None:
        self._timer.stop()
        self._waiting = None
        if self._shown is not None and shiboken6.isValid(self._shown):
            self._shown.hide()
        self._shown = None


_tips: _Tips | None = None


def set_rich_tip(widget: QWidget, title: str, body: str = "", key: str = "", side: str = "right") -> None:
    """Dá a `widget` a dica rica: `title` (o nome), `key` (a tecla, à direita), `body` (uma
    frase; "\\n" separa linhas) e o lado preferido ("right", "left" ou "below")."""
    global _tips
    if _tips is None:
        _tips = _Tips()
    widget.setProperty("ofTipTitle", title)
    widget.setProperty("ofTipBody", body)
    widget.setProperty("ofTipKey", key)
    widget.setProperty("ofTipSide", side)
    heading = f"<b>{html.escape(title)} ({html.escape(key)})</b>" if key else f"<b>{html.escape(title)}</b>"
    lines = [html.escape(line) for line in body.splitlines()]
    widget.setToolTip("<br>".join([heading, *lines]))
    widget.setAccessibleDescription(body)
    widget.removeEventFilter(_tips)
    widget.installEventFilter(_tips)


def shown_tip(window: QWidget) -> RichTip | None:
    """O cartão visível da janela, se houver (para os testes)."""
    tip = window.findChild(RichTip, options=Qt.FindChildOption.FindDirectChildrenOnly)
    return tip if tip is not None and tip.isVisible() else None
