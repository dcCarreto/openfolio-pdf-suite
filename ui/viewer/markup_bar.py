"""A barra de marcação: flutua sobre o visualizador enquanto Anotações está aberta, com as
ferramentas, a cor, a espessura, o número de pendentes e "Gravar"."""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import motion, theme
from ui.annotation_state import TOOLS, AnnotationState
from ui.i18n import EN_US, get_language, tr
from ui.top_bar import bar_separator
from ui.viewer.viewer_icons import build_check_icon, build_markup_icon, build_minus_icon, build_plus_icon

TOOL_LABELS = {
    "select": "Selecionar/Apagar",
    "highlight": "Realce",
    "underline": "Sublinhado",
    "strikeout": "Riscado",
    "note": "Nota adesiva",
    "ink": "Caneta",
    "square": "Retângulo",
    "circle": "Círculo",
    "arrow": "Seta",
    "stamp": "Carimbo",
}
# O nome no botão da ferramenta ativa, quando o completo não cabe (fica na dica e no leitor
# de tela).
SHORT_LABELS = {"select": "Selecionar"}
DEFAULT_KEYS = dict(zip(TOOLS, "VHUSNPROAK"))
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
TOP = 12  # distância do topo do visualizador
TOP_INSET = 64  # margem extra da página com a barra aberta
TOOL_SIZE = 32


def format_width(width: float) -> str:
    text = f"{width:g}"
    return f"{text if get_language() == EN_US else text.replace('.', ',')} pt"


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
                check = QColor("#ffffff") if fill.lightnessF() < 0.5 else QColor("#161826")
                pen = QPen(check, 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPolyline([center + QPointF(-4, 0), center + QPointF(-1, 3), center + QPointF(4, -3)])
        if self.isChecked() or self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent"]), 2))
            painter.drawEllipse(circle.adjusted(-2.5, -2.5, 2.5, 2.5))


class _StyleButton(QToolButton):
    """Modo compacto: a cor e a espessura num botão só (círculo, traço e seta)."""

    def __init__(self, state: AnnotationState, parent=None):
        super().__init__(parent)
        self._state = state
        self.setFixedSize(52, TOOL_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        t = theme.tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(t["border_strong"]), 1))
        painter.setBrush(QColor(f"#{self._state.active_color()}"))
        painter.drawEllipse(QRectF(6, 8, 16, 16))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t["text2"]))
        height = max(1.0, min(8.0, self._state.width() / 1.5))
        painter.drawRoundedRect(QRectF(26, 16 - height / 2, 12, height), height / 2, height / 2)
        pen = QPen(QColor(t["text2"]), 1.5)
        painter.setPen(pen)
        painter.drawPolyline([QPointF(42, 14), QPointF(45, 17), QPointF(48, 14)])


class MarkupBar(QFrame):
    """Filha do viewport do visualizador, fora de qualquer layout: centralizada a 12 px do
    topo e reposicionada quando ele muda de tamanho. Quem a mostra é a aba do documento."""

    save_requested = Signal()

    def __init__(self, state: AnnotationState, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("MarkupBar")
        self.setFixedHeight(48)
        self._state = state
        self._compact: bool | None = None  # None até o primeiro set_compact
        self._right_inset = 0
        self._keys = dict(DEFAULT_KEYS)
        self._faded = False
        self._shown_tool: str | None = None  # a que está aberta (com o nome) agora
        self._active_target = TOOL_SIZE  # a largura final do botão da ferramenta ativa
        self._full_width: int | None = None  # a largura da barra inteira, medida quando preciso

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(4)
        self._layout = layout

        self.tool_buttons: dict[str, QToolButton] = {}
        self._tool_group = QButtonGroup(self)
        self._kbd: dict[str, QLabel] = {}
        tools = QHBoxLayout()
        tools.setSpacing(2)
        for tool in TOOLS:
            if tool == "note":
                tools.addSpacing(2)
                tools.addWidget(bar_separator())
                tools.addSpacing(2)
            button = QToolButton()
            button.setObjectName("MarkupTool")
            button.setIcon(build_markup_icon(tool))
            button.setIconSize(QSize(18, 18))
            button.setCheckable(True)
            button.setFixedHeight(TOOL_SIZE)
            button.setMinimumWidth(TOOL_SIZE)
            button.setMaximumWidth(TOOL_SIZE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=tool: self._state.set_tool(k))
            kbd = QLabel(button)
            kbd.setObjectName("Kbd")
            kbd.setProperty("ofVariant", "accent")
            kbd.hide()
            self._kbd[tool] = kbd
            self._tool_group.addButton(button)
            tools.addWidget(button)
            self.tool_buttons[tool] = button
        layout.addLayout(tools)

        # Cor e espessura: na barra, ou no popover do botão de estilo (modo compacto).
        self.style_group = QWidget()
        style = QHBoxLayout(self.style_group)
        style.setContentsMargins(0, 0, 0, 0)
        style.setSpacing(0)  # as amostras já têm folga de 4 px em volta do círculo
        self.color_buttons: dict[str, ColorSwatch] = {}
        self._color_group = QButtonGroup(self)
        for color, _name in COLORS:
            swatch = ColorSwatch(color)
            swatch.clicked.connect(lambda _checked=False, c=color: self._state.set_color(c))
            self._color_group.addButton(swatch)
            style.addWidget(swatch)
            self.color_buttons[color] = swatch
        self.custom_color_button = ColorSwatch(None)
        self.custom_color_button.clicked.connect(self._choose_color)
        self._color_group.addButton(self.custom_color_button)
        style.addWidget(self.custom_color_button)
        style.addSpacing(4)
        style.addWidget(bar_separator())
        style.addSpacing(4)
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
        self.width_label.setMinimumWidth(42)
        self.width_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.width_up = QToolButton()
        self.width_up.setIcon(build_plus_icon())
        self.width_up.clicked.connect(lambda: self._step_width(WIDTH_STEP))
        for widget in (self.width_down, self.width_up):
            widget.setFixedSize(28, 28)
            widget.setIconSize(QSize(18, 18))
            widget.setStyleSheet("QToolButton { padding: 0; }")  # o do segmentado espremia o ícone
        width_layout.addWidget(self.width_down)
        width_layout.addWidget(self.width_sample)
        width_layout.addWidget(self.width_label)
        width_layout.addWidget(self.width_up)
        style.addWidget(self.width_control)

        self.style_button = _StyleButton(state)
        self.style_button.clicked.connect(self._show_style_popover)
        self.style_popover = QFrame(self, Qt.WindowType.Popup)
        self.style_popover.setObjectName("MarkupPopover")
        self._popover_layout = QVBoxLayout(self.style_popover)
        self._popover_layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(bar_separator())
        layout.addWidget(self.style_group)
        layout.addWidget(self.style_button)
        layout.addWidget(bar_separator())

        # Pendentes e Gravar.
        self.pending_badge = QFrame()
        self.pending_badge.setObjectName("PendingBadge")
        self.pending_badge.setFixedHeight(24)
        badge = QHBoxLayout(self.pending_badge)
        badge.setContentsMargins(4, 0, 6, 0)
        badge.setSpacing(4)
        self.pending_count = QLabel()
        self.pending_count.setObjectName("PendingCount")
        self.pending_count.setFixedSize(16, 16)
        self.pending_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_text = QLabel()
        self.pending_text.setObjectName("PendingText")
        badge.addWidget(self.pending_count)
        badge.addWidget(self.pending_text)
        layout.addWidget(self.pending_badge)
        self.save_button = QPushButton()
        self.save_button.setProperty("ofVariant", "primary")
        self.save_button.setFixedHeight(TOOL_SIZE)
        self.save_button.setStyleSheet("QPushButton { padding: 0 10px; }")  # compacto: cabe em 1440 px
        self.save_button.setIcon(build_check_icon())
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
        self.set_compact(False)
        self.hide()

    # -- textos e atalhos -------------------------------------------------------------

    def retranslate(self):
        self.setAccessibleName(tr("Barra de marcação"))
        for color, name in COLORS:
            self.color_buttons[color].setToolTip(tr(name))
            self.color_buttons[color].setAccessibleName(tr("Cor: {name}").format(name=tr(name)))
        self.custom_color_button.setToolTip(tr("Mais cores..."))
        self.custom_color_button.setAccessibleName(tr("Mais cores..."))
        self.width_down.setToolTip(tr("Diminuir a espessura"))
        self.width_down.setAccessibleName(tr("Diminuir a espessura"))
        self.width_up.setToolTip(tr("Aumentar a espessura"))
        self.width_up.setAccessibleName(tr("Aumentar a espessura"))
        self.style_button.setToolTip(tr("Cor e espessura"))
        self.style_button.setAccessibleName(tr("Cor e espessura"))
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
        previous, self._shown_tool = self._shown_tool, (None if self._compact else active)
        self._full_width = None
        self._active_target = TOOL_SIZE
        for tool, button in self.tool_buttons.items():
            name = tr(TOOL_LABELS[tool])
            key = self._keys.get(tool, "")
            button.setToolTip(f"{name} ({key})" if key else name)
            button.setAccessibleName(name)
            kbd = self._kbd[tool]
            kbd.setText(key)
            is_active = tool == active
            button.setChecked(is_active)
            wide = is_active and not self._compact
            button.setProperty("active", wide)
            button.style().unpolish(button)
            button.style().polish(button)
            button.setText(tr(SHORT_LABELS.get(tool, TOOL_LABELS[tool])) if wide else "")
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon if wide else Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            kbd.setVisible(wide and bool(key))
            kbd.adjustSize()
            # O selo da tecla fica à direita do nome, no espaço reservado pelo padding.
            # Com seletor: sem ele, o padding valeria também para o selo, que é filho do botão.
            padding = f"QToolButton#MarkupTool {{ padding-right: {kbd.width() + 14}px; }}"
            button.setStyleSheet(padding if wide and key else "")
            if wide:
                end = button.sizeHint().width()
                kbd.move(end - kbd.width() - 8, (TOOL_SIZE - kbd.height()) // 2)
                self._active_target = end
                if previous is not None and tool != previous:  # só anima ao trocar de ferramenta
                    grow = motion.animate(button, b"maximumWidth", TOOL_SIZE, end, motion.FAST)
                    if grow is not None:  # a barra cresce junto com o botão
                        grow.valueChanged.connect(lambda _value: self._reposition())
                else:
                    button.setMaximumWidth(end)
            else:
                button.setMaximumWidth(TOOL_SIZE)
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
        self._full_width = None
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
        self.style_button.update()

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

    def _update_pending(self):
        self._full_width = None
        count = len(self._state.pending())
        text = tr("{count} pendentes").format(count=count)
        self.pending_count.setText(str(count))
        self.pending_text.setText(tr("pendentes"))
        self.pending_text.setVisible(not self._compact)
        self.pending_badge.setToolTip(text)
        self.pending_badge.setAccessibleName(text)
        self.pending_badge.setVisible(count > 0)
        self.save_button.setEnabled(count > 0)
        self.save_button.setText("" if self._compact else tr("Gravar"))
        self.save_button.setAccessibleName(tr("Gravar"))
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
        """Abaixo de 1180 px (ou com o centro estreito): só ícones, e cor e espessura num
        popover."""
        if compact == self._compact:
            return
        self._compact = compact
        self.style_button.setVisible(compact)
        if compact:
            self._popover_layout.addWidget(self.style_group)
        else:
            self.style_popover.hide()
            self._layout.insertWidget(self._layout.indexOf(self.style_button), self.style_group)
        self.style_group.show()
        self._update_tool()
        self._update_pending()

    def is_compact(self) -> bool:
        return bool(self._compact)

    def full_width(self) -> int:
        """A largura da barra inteira (fora do modo compacto) no pior caso: o nome mais longo
        na ferramenta ativa e o selo de pendentes à mostra. Quem a posiciona decide por ela se
        a barra cabe, e a barra não muda de modo ao trocar de ferramenta nem com a primeira
        pendente."""
        if self._full_width is None:
            compact = self._compact
            if compact:
                self.set_compact(False)
            tool = self._state.active_tool() or "select"
            active = self.tool_buttons[tool]
            growing = max(0, self._active_target - active.maximumWidth())  # no meio da animação
            font = QFont(active.font())
            font.setPixelSize(12)
            font.setWeight(QFont.Weight.DemiBold)
            metrics = QFontMetrics(font)
            labels = {t: tr(SHORT_LABELS.get(t, TOOL_LABELS[t])) for t in TOOLS}
            longer = max(metrics.horizontalAdvance(text) for text in labels.values())
            longer -= metrics.horizontalAdvance(labels[tool])
            badge = 0 if self.pending_badge.isVisibleTo(self) else self.pending_badge.sizeHint().width() + 4
            width = self.sizeHint().width() + growing + longer + badge
            if compact:
                self.set_compact(True)
            self._full_width = width
        return self._full_width

    def _show_style_popover(self):
        self.style_popover.adjustSize()
        self.style_popover.move(self.style_button.mapToGlobal(QPoint(0, self.style_button.height() + 6)))
        self.style_popover.show()

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
