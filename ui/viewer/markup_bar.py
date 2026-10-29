"""A barra de marcação: flutua sobre o visualizador enquanto Anotações está aberta, numa linha só
e em grupos: Selecionar | Realce ▾, Nota, Caneta, Formas ▾, Carimbo | Estilo ▾ | pendentes e
"Gravar". Sublinhado e riscado ficam no ▾ do Realce; retângulo, círculo e seta, no das Formas; a
cor e a espessura, no popover do Estilo."""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import motion, theme
from ui.annotation_state import TOOLS, AnnotationState
from ui.i18n import EN_US, get_language, plural, tr
from ui.top_bar import bar_separator
from ui.viewer.viewer_icons import build_caret_down_icon, build_markup_icon, build_minus_icon, build_plus_icon

TOOL_LABELS = {
    "select": "Selecionar",
    "highlight": "Realce",
    "underline": "Sublinhado",
    "strikeout": "Riscado",
    "note": "Nota",
    "ink": "Caneta",
    "square": "Retângulo",
    "circle": "Círculo",
    "arrow": "Seta",
    "stamp": "Carimbo",
}
# A frase da dica de cada ferramenta: o que ela faz na página.
TOOL_PHRASES = {
    "select": "Clique numa marcação para escolhê-la; arraste para movê-la.",
    "highlight": "Arraste sobre o texto para realçá-lo.",
    "underline": "Arraste sobre o texto para sublinhá-lo.",
    "strikeout": "Arraste sobre o texto para riscá-lo.",
    "note": "Clique na página para deixar um comentário.",
    "ink": "Desenhe à mão livre sobre a página.",
    "square": "Arraste para desenhar um retângulo.",
    "circle": "Arraste para desenhar um círculo.",
    "arrow": "Arraste para desenhar uma seta.",
    "stamp": "Clique na página para pôr o carimbo escolhido no painel.",
}
DEFAULT_KEYS = dict(zip(TOOLS, "VHUSNPROAK"))
# Os botões da barra, na ordem; os de mais de uma ferramenta têm o ▾ com as outras.
GROUPS = [
    ("select",),
    ("highlight", "underline", "strikeout"),
    ("note",),
    ("ink",),
    ("square", "circle", "arrow"),
    ("stamp",),
]
MORE_LABELS = {"highlight": "Sublinhado e riscado", "square": "Círculo e seta"}  # o ▾ de cada grupo
COLORS = [
    ("ffeb3b", "Amarelo"),
    ("f44336", "Vermelho"),
    ("4caf50", "Verde"),
    ("2196f3", "Azul"),
    ("000000", "Preto"),
]
TEXT_TOOLS = ("highlight", "underline", "strikeout")  # seguem a linha do texto: sem espessura
WIDTH_RANGE = (0.5, 20.0)
WIDTH_STEP = 0.5
TOP = 10  # distância do topo do visualizador
TOP_INSET = 64  # margem extra da página com a barra aberta
TOOL_SIZE = 32
SPLIT_WIDTH = 14  # a área do ▾ nos botões de grupo


def format_width(width: float) -> str:
    text = f"{width:g}"
    return f"{text if get_language() == EN_US else text.replace('.', ',')} pt"


def tool_tip(tool: str, key: str) -> str:
    """A dica rica: o nome, a tecla e o que a ferramenta faz."""
    title = f"<b>{tr(TOOL_LABELS[tool])}</b>" + (f"&nbsp;&nbsp;({key})" if key else "")
    return f"{title}<br>{tr(TOOL_PHRASES[tool])}"


class ColorSwatch(QToolButton):
    """Uma cor (círculo de 16 px numa área de clique de 28): a escolhida ganha anel e "✓",
    para não depender só da cor. Sem cor, é o "+" que abre o seletor."""

    def __init__(self, color: str | None, parent=None):
        super().__init__(parent)
        self.color = color
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        t = theme.tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        circle = QRectF(center.x() - 8, center.y() - 8, 16, 16)
        if self.color is None:
            painter.setPen(QPen(QColor(t["text2"]), 1.5))
            painter.drawEllipse(circle.adjusted(0.75, 0.75, -0.75, -0.75))
            painter.drawLine(QPointF(center.x() - 4, center.y()), QPointF(center.x() + 4, center.y()))
            painter.drawLine(QPointF(center.x(), center.y() - 4), QPointF(center.x(), center.y() + 4))
        else:
            fill = QColor(f"#{self.color}")
            painter.setPen(QPen(QColor(t["border_strong"]), 1))
            painter.setBrush(fill)
            painter.drawEllipse(circle)
            if self.isChecked():
                painter.setBrush(Qt.BrushStyle.NoBrush)
                check = QColor("#ffffff") if fill.lightnessF() < 0.5 else QColor("#141b25")
                pen = QPen(check, 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPolyline([center + QPointF(-4, 0), center + QPointF(-1, 3), center + QPointF(4, -3)])
        if self.isChecked() or self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent"] if self.isChecked() else t["focus"]), 2))
            painter.drawEllipse(circle.adjusted(-2.5, -2.5, 2.5, 2.5))


class ToolGroup(QWidget):
    """Um botão da barra. Com mais de uma ferramenta (Realce, Formas), o botão mostra a última
    escolhida do grupo e tem o ▾ embutido, que abre as outras (a seta para baixo também abre,
    pelo teclado): uma peça só, de 46 x 32, para o alvo de clique não ficar estreito."""

    chosen = Signal(str)

    def __init__(self, tools: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.tools = tools
        self.current = tools[0]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.button = QToolButton()
        self.button.setObjectName("MarkupTool")
        self.button.setIconSize(QSize(18, 18))
        self.button.setCheckable(True)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setProperty("split", len(tools) > 1)
        self.button.clicked.connect(lambda: self.chosen.emit(self.current))
        layout.addWidget(self.button)
        self.menu: QMenu | None = None
        self.tool_actions: dict = {}
        if len(tools) > 1:
            self.menu = QMenu(self)
            for tool in tools:
                action = self.menu.addAction(build_markup_icon(tool), "")
                action.setCheckable(True)
                action.triggered.connect(lambda _checked=False, t=tool: self.chosen.emit(t))
                self.tool_actions[tool] = action
            self.button.setMenu(self.menu)
            self.button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            self.button.installEventFilter(self)
        self.button.setFixedSize(TOOL_SIZE + (SPLIT_WIDTH if self.menu else 0), TOOL_SIZE)
        self.set_active(None)

    def show_menu(self) -> None:
        if self.menu is not None:
            self.button.showMenu()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            self.show_menu()
            return True
        return super().eventFilter(watched, event)

    def set_active(self, active: str | None) -> None:
        if active in self.tools:
            self.current = active
        self.button.setIcon(build_markup_icon(self.current))
        self.button.setChecked(active in self.tools)
        for tool, action in self.tool_actions.items():
            action.setChecked(tool == active)

    def retranslate(self, keys: dict[str, str]) -> None:
        name = tr(TOOL_LABELS[self.current])
        tip = tool_tip(self.current, keys.get(self.current, ""))
        if self.menu is not None:
            more = tr(MORE_LABELS[self.tools[0]])
            tip += "<br>" + tr("{more}: no ▾ (ou seta para baixo).").format(more=more)
        self.button.setToolTip(tip)
        self.button.setAccessibleName(name)
        for tool, action in self.tool_actions.items():
            key = keys.get(tool, "")
            action.setText(f"{tr(TOOL_LABELS[tool])}	{key}" if key else tr(TOOL_LABELS[tool]))


class StyleButton(QToolButton):
    """Estilo: a bolinha da cor atual, a espessura ("2,5 pt") e o ▾ que abre o popover. Na
    barra compacta, só a bolinha e o ▾."""

    def __init__(self, state: AnnotationState, parent=None):
        super().__init__(parent)
        self.setObjectName("MarkupTool")
        self._state = state
        self._compact = False
        self.setFixedHeight(TOOL_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedWidth(self.width_for(compact))
        self.update()

    def width_for(self, compact: bool) -> int:
        """Bolinha, o texto (fora do compacto) e o ▾, com as folgas."""
        text = 0 if compact else QFontMetrics(self._font()).horizontalAdvance(self._text()) + 4
        return 8 + 14 + 6 + text + 12 + 6

    def _text(self) -> str:
        return format_width(self._state.width())

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12)
        return font

    def refresh(self) -> None:
        self.setFixedWidth(self.width_for(self._compact))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)  # o fundo (mouse, pressionado) vem do estilo
        t = theme.tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(t["border_strong"]), 1))
        painter.setBrush(QColor(f"#{self._state.active_color()}"))
        middle = self.height() / 2
        painter.drawEllipse(QRectF(8, middle - 7, 14, 14))
        if not self._compact:
            painter.setFont(self._font())
            painter.setPen(QColor(t["text2"]))
            text = QRect(8 + 14 + 6, 0, self.width() - (8 + 14 + 6) - 18, self.height())
            painter.drawText(text, Qt.AlignmentFlag.AlignVCenter, self._text())
        build_caret_down_icon().paint(painter, QRect(self.width() - 18, int(middle) - 6, 12, 12))


class MarkupBar(QFrame):
    """Filha do viewport do visualizador, fora de qualquer layout: centralizada a 10 px do
    topo e reposicionada quando ele muda de tamanho. Quem a mostra é a aba do documento."""

    save_requested = Signal()

    def __init__(self, state: AnnotationState, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("MarkupBar")
        self._state = state
        self._compact = False
        self._right_inset = 0
        self._keys = dict(DEFAULT_KEYS)
        self._faded = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self._layout = layout

        self.groups: list[ToolGroup] = []
        self.group_of: dict[str, ToolGroup] = {}
        for tools in GROUPS:
            group = ToolGroup(tools)
            group.chosen.connect(self._choose)
            if tools[0] == "highlight":
                layout.addWidget(self._separator())
            layout.addWidget(group)
            self.groups.append(group)
            for tool in tools:
                self.group_of[tool] = group
        layout.addWidget(self._separator())

        # Estilo: a cor e a espessura num popover.
        self.style_button = StyleButton(state)
        self.style_button.clicked.connect(self._show_style_popover)
        layout.addWidget(self.style_button)
        self.style_popover = QFrame(self, Qt.WindowType.Popup)
        self.style_popover.setObjectName("MarkupPopover")
        popover = QVBoxLayout(self.style_popover)
        popover.setContentsMargins(12, 10, 12, 12)
        popover.setSpacing(8)
        self.style_group = QWidget()
        style = QVBoxLayout(self.style_group)
        style.setContentsMargins(0, 0, 0, 0)
        style.setSpacing(8)
        self._color_title = QLabel()
        self._color_title.setProperty("ofRole", "section")
        swatches = QHBoxLayout()
        swatches.setSpacing(0)  # as amostras já têm folga de 4 px em volta do círculo
        self.color_buttons: dict[str, ColorSwatch] = {}
        self._color_group = QButtonGroup(self)
        for color, _name in COLORS:
            swatch = ColorSwatch(color)
            swatch.clicked.connect(lambda _checked=False, c=color: self._state.set_color(c))
            self._color_group.addButton(swatch)
            swatches.addWidget(swatch)
            self.color_buttons[color] = swatch
        self.custom_color_button = ColorSwatch(None)
        self.custom_color_button.clicked.connect(self._choose_color)
        self._color_group.addButton(self.custom_color_button)
        swatches.addWidget(self.custom_color_button)
        swatches.addStretch()
        self._width_title = QLabel()
        self._width_title.setProperty("ofRole", "section")
        self.width_control = QWidget()
        self.width_control.setObjectName("Segmented")
        self.width_control.setFixedHeight(TOOL_SIZE)
        width_layout = QHBoxLayout(self.width_control)
        width_layout.setContentsMargins(2, 2, 2, 2)
        width_layout.setSpacing(2)
        self.width_down = QToolButton()
        self.width_down.setIcon(build_minus_icon())
        self.width_down.clicked.connect(lambda: self._step_width(-WIDTH_STEP))
        self.width_sample = QLabel()
        self.width_label = QLabel()
        self.width_label.setMinimumWidth(48)
        self.width_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.width_up = QToolButton()
        self.width_up.setIcon(build_plus_icon())
        self.width_up.clicked.connect(lambda: self._step_width(WIDTH_STEP))
        for widget in (self.width_down, self.width_up):
            widget.setFixedSize(28, 28)
            widget.setIconSize(QSize(18, 18))
            widget.setStyleSheet("QToolButton { padding: 0; }")  # o do segmentado espremia o ícone
        width_layout.addWidget(self.width_down)
        width_layout.addStretch()
        width_layout.addWidget(self.width_sample)
        width_layout.addWidget(self.width_label)
        width_layout.addStretch()
        width_layout.addWidget(self.width_up)
        style.addWidget(self._color_title)
        style.addLayout(swatches)
        style.addWidget(self._width_title)
        style.addWidget(self.width_control)
        popover.addWidget(self.style_group)
        layout.addWidget(self._separator())

        # Pendentes e Gravar.
        self.pending_label = QLabel()
        self.pending_label.setObjectName("PendingText")
        layout.addSpacing(4)
        layout.addWidget(self.pending_label)
        layout.addSpacing(4)
        self.save_button = QPushButton()
        self.save_button.setProperty("ofVariant", "primary")
        self.save_button.setProperty("ofSize", "compact")
        self.save_button.setFixedHeight(28)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_requested)
        layout.addWidget(self.save_button)

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.setInterval(1500)
        self._fade_timer.timeout.connect(self._fade_out)

        state.tool_changed.connect(self._update_tool)
        state.style_changed.connect(self._update_style)
        state.pending_changed.connect(self._update_pending)
        parent.installEventFilter(self)
        self.setGraphicsEffect(theme.floating_shadow(self))
        self.retranslate()
        self.hide()

    @staticmethod
    def _separator() -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(bar_separator())
        return holder

    def button_for(self, tool: str) -> QToolButton:
        """O botão que leva à ferramenta (o do grupo dela, para sublinhado, círculo...)."""
        return self.group_of[tool].button

    def choose(self, tool: str) -> None:
        """Como escolher a ferramenta na barra (no botão ou no ▾ do grupo)."""
        self._choose(tool)

    def _choose(self, tool: str) -> None:
        self._state.set_tool(tool)
        self._update_tool()  # clicar na já escolhida não muda o estado, mas o botão desmarcou

    # -- textos e atalhos -------------------------------------------------------------

    def retranslate(self):
        self.setAccessibleName(tr("Barra de marcação"))
        for color, name in COLORS:
            self.color_buttons[color].setToolTip(tr(name))
            self.color_buttons[color].setAccessibleName(tr("Cor: {name}").format(name=tr(name)))
        self.custom_color_button.setToolTip(tr("Mais cores..."))
        self.custom_color_button.setAccessibleName(tr("Mais cores..."))
        self._color_title.setText(tr("Cor"))
        self._width_title.setText(tr("Espessura"))
        self.width_down.setToolTip(tr("Diminuir a espessura"))
        self.width_down.setAccessibleName(tr("Diminuir a espessura"))
        self.width_up.setToolTip(tr("Aumentar a espessura"))
        self.width_up.setAccessibleName(tr("Aumentar a espessura"))
        self.style_button.setToolTip(f"<b>{tr('Estilo')}</b><br>{tr('A cor e a espessura das próximas marcações.')}")
        self.style_button.setAccessibleName(tr("Estilo: cor e espessura"))
        self.save_button.setText(tr("Gravar"))
        self.save_button.setToolTip(tr("Gravar as marcações pendentes como uma versão do documento (Ctrl+Z desfaz)"))
        self._update_tool()
        self._update_style()
        self._update_pending()

    def set_keys(self, keys: dict[str, str]) -> None:
        """As teclas de cada ferramenta (configuráveis em Editar > Atalhos de teclado)."""
        self._keys = {tool: keys.get(tool, "") for tool in TOOLS}
        self._update_tool()

    # -- estado -----------------------------------------------------------------------

    def _update_tool(self):
        active = self._state.active_tool() or "select"
        for group in self.groups:
            group.set_active(active)
            group.retranslate(self._keys)
        text_tool = active in TEXT_TOOLS
        self.width_control.setEnabled(not text_tool)
        self.width_control.setToolTip(
            tr("Realce, sublinhado e riscado seguem a linha do texto: a espessura vale para caneta, formas e seta.")
            if text_tool
            else tr("Espessura")
        )
        self._restore_opacity()
        self._reposition()

    def _update_style(self):
        color = self._state.active_color()
        swatch = self.color_buttons.get(color)
        if swatch is None:
            self.custom_color_button.color = color
            self.custom_color_button.setChecked(True)
            self.custom_color_button.setAccessibleName(tr("Cor: {name}").format(name=f"#{color}"))
        else:
            self.custom_color_button.color = None
            swatch.setChecked(True)
        self.custom_color_button.update()
        width = self._state.width()
        self.width_label.setText(format_width(width))
        self.width_label.setAccessibleName(tr("Espessura: {width}").format(width=format_width(width)))
        self.width_down.setEnabled(width > WIDTH_RANGE[0])
        self.width_up.setEnabled(width < WIDTH_RANGE[1])
        self.width_sample.setPixmap(self._sample(width))
        self.style_button.refresh()
        self._reposition()

    def _sample(self, width: float) -> QPixmap:
        ratio = self.devicePixelRatioF() or 1.0
        pixmap = QPixmap(QSize(14, 16) * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.tokens()["text"]))
        height = max(1.0, min(10.0, width / 1.5))
        painter.drawRoundedRect(QRectF(0, 8 - height / 2, 14, height), height / 2, height / 2)
        painter.end()
        return pixmap

    def pending_text(self, count: int, compact: bool | None = None) -> str:
        """"2 pendentes"; na barra compacta, só o número."""
        compact = self._compact if compact is None else compact
        return str(count) if compact else plural(count, "1 pendente", "{count} pendentes")

    def _update_pending(self):
        count = len(self._state.pending())
        self.pending_label.setText(self.pending_text(count))
        full = plural(count, "1 pendente", "{count} pendentes")
        self.pending_label.setToolTip(full)
        self.pending_label.setAccessibleName(full)
        self.pending_label.setVisible(count > 0)
        self.save_button.setEnabled(count > 0)
        self._reposition()

    def _step_width(self, delta: float):
        low, high = WIDTH_RANGE
        self._state.set_width(min(high, max(low, round((self._state.width() + delta) * 2) / 2)))

    def _choose_color(self):
        current = QColor(f"#{self._state.active_color()}")
        color = QColorDialog.getColor(current, self.window(), tr("Cor da marcação"))
        if color.isValid():
            self._state.set_color(color.name()[1:])
        self._update_style()  # cancelado: a marca volta para a cor que estava

    # -- modo compacto e posição -------------------------------------------------------

    def set_compact(self, compact: bool) -> None:
        """Sem espaço para a barra inteira (janela estreita, gaveta aberta): o Estilo fica só
        com a bolinha e o contador só com o número."""
        if compact == self._compact:
            return
        self._compact = compact
        self.style_button.set_compact(compact)
        self._update_pending()

    def is_compact(self) -> bool:
        return self._compact

    def full_width(self) -> int:
        """A largura da barra inteira, com o Estilo e o contador por extenso, no pior caso (com
        pendentes): quem a posiciona decide por ela se a barra cabe, e a barra não muda de modo
        com a primeira pendente."""
        width = self.sizeHint().width()
        metrics = self.pending_label.fontMetrics()
        longest = metrics.horizontalAdvance(self.pending_text(99, compact=False))
        if self.pending_label.isVisibleTo(self):
            width -= self.pending_label.sizeHint().width()
        else:
            width += self._layout.spacing()
        width += longest
        if self._compact:
            width += self.style_button.width_for(False) - self.style_button.width_for(True)
        return width

    def _show_style_popover(self):
        self.style_popover.adjustSize()
        self.style_popover.move(self.style_button.mapToGlobal(QPoint(0, self.style_button.height() + 6)))
        self.style_popover.show()
        motion.animate(self.style_popover, b"windowOpacity", 0.0, 1.0, motion.MEDIUM)

    def set_right_inset(self, inset: int) -> None:
        """Com a gaveta da ferramenta aberta, centraliza na parte visível à esquerda dela."""
        self._right_inset = inset
        self._reposition()

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        available = max(0, parent.width() - self._right_inset)
        self.move(max(2, (available - self.width()) // 2), TOP)
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._reposition()
        return False

    # -- aparecer e esmaecer -----------------------------------------------------------

    def appear(self) -> None:
        if self.isVisible():
            return
        self._reposition()
        self.show()
        self._animate_opacity(0.0, 1.0, motion.FAST)

    def note_scroll(self) -> None:
        """O documento rolou: com Selecionar, a barra esmaece depois de 1,5 s parada."""
        if self.isVisible() and motion.enabled() and (self._state.active_tool() or "select") == "select":
            self._fade_timer.start()

    def _fade_out(self):
        if self.isVisible() and not self.underMouse() and not self._faded:
            self._faded = True
            self._animate_opacity(1.0, 0.55, motion.MEDIUM)

    def _restore_opacity(self):
        self._fade_timer.stop()
        if self._faded:
            self._faded = False
            self._animate_opacity(0.55, 1.0, motion.MEDIUM)

    def _animate_opacity(self, start: float, end: float, ms: int):
        # Um efeito por vez: a opacidade enquanto anima ou está esmaecida, a sombra em repouso.
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(start)
        self.setGraphicsEffect(effect)
        done = (lambda: self.setGraphicsEffect(theme.floating_shadow(self))) if end >= 1.0 else None
        motion.animate(effect, b"opacity", start, end, ms, on_done=done)

    def enterEvent(self, event):
        self._restore_opacity()
        super().enterEvent(event)
