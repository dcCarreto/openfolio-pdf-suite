"""O painel de ferramenta: um padrão só para todas as ferramentas.

    [ícone] Título                                        [x]
            descrição, em até duas linhas
    ─────────────────────────────────────────────────────────
    Arquivo                  o PDF aberto
    (rótulo da ferramenta)   os controles dela
    Onde fica o resultado    Neste documento | Em um arquivo novo
    ─────────────────────────────────────────────────────────
    [            ação principal              Ctrl+Enter ]

O rodapé tem cinco estados: pronto, vazio (sem o PDF de entrada: "Abra um PDF para continuar."
e a ação desabilitada), ocupado (andamento e "Cancelar", com o conteúdo esmaecido), sucesso e
erro (o cartão de resultado no lugar dos diálogos).

A ferramenta continua dona dos widgets e da lógica dela. O painel só os arruma: tira da página
o `source_bar` (entrada) e o `output_picker` (saída), com o rótulo logo antes de cada um, e
mostra no rodapé um botão que faz o papel do botão de ação do modo visível
(`page.action_buttons`, um por modo), com o mesmo texto e habilitado quando ele estiver.
"""

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import motion, theme
from ui.i18n import tr
from ui.viewer.viewer_icons import build_close_icon
from ui.widgets.segmented import Segmented

MODES_WIDTH = 312  # o que cabe no painel de 340 px: mais largo que isso, os modos viram um combo

READY, EMPTY, BUSY, SUCCESS, ERROR, INFO = "ready", "empty", "busy", "success", "error", "info"


def _result_icon(kind: str, size: int = 20) -> QPixmap:
    """Círculo cheio com "✓" (sucesso), "!" (erro) ou "i" (aviso): a forma diz o que é, não
    só a cor."""
    t = theme.tokens()
    color = QColor({SUCCESS: t["success"], ERROR: t["danger"]}.get(kind, t["text2"]))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    pen = QPen(QColor(t["panel"]), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.scale(size / 20, size / 20)
    if kind == SUCCESS:
        painter.drawPolyline([QPointF(6, 10.5), QPointF(9, 13.5), QPointF(14, 7.5)])
    elif kind == ERROR:
        painter.drawLine(QPointF(10, 5.5), QPointF(10, 11))
        painter.drawPoint(QPointF(10, 14.5))
    else:
        painter.drawPoint(QPointF(10, 6))
        painter.drawLine(QPointF(10, 9.5), QPointF(10, 14.5))
    painter.end()
    return pixmap


class ResultCard(QFrame):
    """O resultado da operação: ícone, resumo e detalhes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("ofRole", "result")
        self.icon = QLabel()
        self.icon.setFixedSize(20, 20)
        self.title = QLabel()
        self.title.setObjectName("ResultTitle")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details = QLabel()
        self.details.setProperty("ofRole", "secondary")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # O texto técnico do erro (para anexar a uma issue) fica recolhido, como no diálogo antigo.
        self.technical = QLabel()
        self.technical.setProperty("ofRole", "secondary")
        self.technical.setWordWrap(True)
        self.technical.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.technical_button = QPushButton(tr("Ver detalhes"))
        self.technical_button.setProperty("ofVariant", "ghost")
        self.technical_button.setProperty("ofTone", "danger")
        self.technical_button.setProperty("ofSize", "mini")
        self.technical_button.setCheckable(True)
        self.technical_button.toggled.connect(self.technical.setVisible)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title)
        text.addWidget(self.details)
        text.addWidget(self.technical_button, 0, Qt.AlignmentFlag.AlignLeft)
        text.addWidget(self.technical)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)

    def show_result(self, kind: str, title: str, details: str, technical: str = "") -> None:
        self.setProperty("state", kind)
        self.style().unpolish(self)
        self.style().polish(self)
        self.icon.setPixmap(_result_icon(kind))
        self.title.setText(title)
        self.details.setText(details)
        self.details.setVisible(bool(details))
        self.technical.setText(technical)
        self.technical_button.setChecked(False)
        self.technical.hide()
        self.technical_button.setVisible(bool(technical))
        self.setAccessibleName(f"{title} {details}".strip())


class _Watcher(QObject):
    """Avisa quando um botão de ação muda de habilitado ou quando um modo aparece/some."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.EnabledChange, QEvent.Type.ShowToParent, QEvent.Type.HideToParent):
            self._callback()
        return False


def _containing_layout(layout: QLayout, widget: QWidget) -> QLayout | None:
    if layout.indexOf(widget) >= 0:
        return layout
    for index in range(layout.count()):
        item = layout.itemAt(index)
        child = item.layout() if item is not None else None
        if child is not None and (found := _containing_layout(child, widget)) is not None:
            return found
    return None


def _take_out(page: QWidget, widget: QWidget) -> None:
    """Tira `widget` do formulário da página, com o rótulo simples logo antes dele."""
    page_layout = page.layout()
    layout = _containing_layout(page_layout, widget) if page_layout is not None else None
    if layout is None:
        return
    index = layout.indexOf(widget)
    before = layout.itemAt(index - 1) if index > 0 else None
    label = before.widget() if before is not None else None
    layout.removeWidget(widget)
    if isinstance(label, QLabel) and not label.objectName():
        layout.removeWidget(label)
        label.hide()


class ToolPanel(QFrame):
    close_requested = Signal()

    def __init__(self, icon: QIcon, title: str, description: str, page: QWidget, session, tasks, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolPanel")
        self.page = page
        self.session = session
        self._tasks = tasks
        self._state = READY
        self.modes_widget: Segmented | QComboBox | None = None
        self._actions: list[QPushButton] = list(getattr(page, "action_buttons", []))
        input_widget = getattr(page, "source_bar", None)
        output_widget = getattr(page, "output_picker", None)
        self._needs_document = input_widget is not None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header(icon, title, description))

        # Corpo: as seções, na ordem Entrada, Opções, Saída.
        self.body = QWidget()
        self.body.setObjectName("ToolBody")
        self._sections = QVBoxLayout(self.body)
        self._sections.setContentsMargins(16, 16, 16, 12)
        self._sections.setSpacing(20)
        for widget in (input_widget, output_widget):
            if widget is not None:
                _take_out(page, widget)
        if (page_layout := page.layout()) is not None:
            page_layout.setContentsMargins(0, 0, 0, 0)
        if input_widget is not None:
            self.add_section(tr("Arquivo"), input_widget)
        # Uma seção própria da ferramenta, com título que ela mesma atualiza (os comentários
        # de Anotações): entre a entrada e as opções.
        extra = getattr(page, "extra_section", None)
        if extra is not None:
            self.add_section("", extra[1], label=extra[0])
        # O rótulo das opções é o da ferramenta ("Quanto comprimir"), se ela tiver um.
        options_label = self.add_section(tr(getattr(page, "options_title", "Opções")), page)
        if output_widget is not None:
            self.add_section(tr("Onde fica o resultado"), output_widget)
        # Os botões da ação e os do rodapé ("Descartar") saem da página: não contam como opções.
        leaving = [*self._actions, *getattr(page, "footer_buttons", [])]
        if not any(child.isVisibleTo(page) and child not in leaving for child in page.findChildren(QWidget)):
            options_label.hide()  # sem opções (Extrair texto): a seção não aparece vazia
            page.hide()
        self._sections.addStretch(1)  # a sobra fica embaixo, e não entre as seções
        scroll = self.scroll_area = QScrollArea()
        scroll.setObjectName("ToolScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.body)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._build_footer())

        self._watcher = _Watcher(self._refresh_ready, self)
        for button in self._actions:
            button.hide()  # o botão do rodapé faz o papel dele
            button.installEventFilter(self._watcher)
            if (mode := button.parentWidget()) is not None:
                mode.installEventFilter(self._watcher)
        # Botões a mais no rodapé, antes do principal ("Descartar" em Anotações).
        for button in reversed(getattr(page, "footer_buttons", [])):
            _take_out(page, button)
            self._ready_row.insertWidget(0, button)
            # Dividindo a linha, o botão não tem lugar para o atalho: ele vai para a dica.
            self.primary_kbd.hide()
            self.primary_button.setToolTip("Ctrl+Enter")
        edits_changed = getattr(page, "edits_changed", None)
        if edits_changed is not None:  # o texto do botão da ação muda com as edições
            edits_changed.connect(self._refresh_ready)
        session.path_changed.connect(self._refresh_ready)
        session.history_changed.connect(self._refresh_ready)
        self._refresh_ready()

    # -- montagem ---------------------------------------------------------------------

    def _build_header(self, icon: QIcon, title: str, description: str) -> QWidget:
        header = QWidget()
        header.setObjectName("ToolHeader")
        tile = QLabel()
        tile.setObjectName("IconTile")
        tile.setFixedSize(32, 32)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(icon.pixmap(QSize(18, 18), QIcon.Mode.Selected))
        self.title_label = QLabel(title)
        self.title_label.setObjectName("ToolTitle")
        # A descrição quebra em até duas linhas, sem reticências (os textos são escritos curtos).
        self.description_label = QLabel(description)
        self.description_label.setProperty("ofRole", "secondary")
        self.description_label.setWordWrap(True)
        self.description_label.setMinimumWidth(40)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.title_label)
        texts.addWidget(self.description_label)
        self.close_button = QToolButton()
        self.close_button.setObjectName("ToolClose")
        self.close_button.setProperty("ofRole", "icon")
        self.close_button.setIcon(build_close_icon())
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip(tr("Fechar ferramenta (Esc)"))
        self.close_button.setAccessibleName(tr("Fechar ferramenta (Esc)"))
        self.close_button.clicked.connect(self.close_requested)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(texts, 1)
        row.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        # Abaixo da linha do título, o segmentado dos modos (quando a ferramenta tem).
        self.header_layout = QVBoxLayout(header)
        self.header_layout.setContentsMargins(16, 12, 12, 12)
        self.header_layout.setSpacing(12)
        self.header_layout.addLayout(row)
        return header

    def set_modes(self, labels: list[str], current: int, choose) -> None:
        """Os modos da ferramenta, abaixo do título: um segmentado se forem até 4 e couberem,
        senão um combo. `choose(índice)` troca de modo."""
        if len(labels) < 2:
            return
        segmented = Segmented(labels)
        widget: Segmented | QComboBox
        if len(labels) <= 4 and segmented.sizeHint().width() <= MODES_WIDTH:
            segmented.chosen.connect(choose)
            widget = segmented
        else:
            segmented.deleteLater()
            widget = QComboBox()
            widget.setObjectName("ModesCombo")
            widget.addItems(labels)
            widget.activated.connect(choose)
        widget.setAccessibleName(tr("Modo"))
        self.modes_widget = widget
        self.header_layout.addWidget(widget)
        self.set_current_mode(current)

    def set_current_mode(self, index: int) -> None:
        widget = self.modes_widget
        if isinstance(widget, Segmented):
            widget.set_current(index)
        elif widget is not None:
            widget.setCurrentIndex(index)

    def current_mode(self) -> int:
        widget = self.modes_widget
        if isinstance(widget, Segmented):
            return widget.current()
        return widget.currentIndex() if widget is not None else 0

    def add_section(self, title: str, widget: QWidget, label: QWidget | None = None) -> QWidget:
        """Uma seção: o rótulo (ou um cabeçalho da ferramenta, com controles à direita) e o
        conteúdo."""
        if label is None:
            label = QLabel(title)
            label.setProperty("ofRole", "section")
        section = QVBoxLayout()
        section.setSpacing(8)
        section.addWidget(label)
        section.addWidget(widget)
        self._sections.addLayout(section)
        return label

    def _build_footer(self) -> QWidget:
        self.footer = QStackedWidget()
        self.footer.setObjectName("ToolFooter")

        ready = QWidget()
        self.primary_button = QPushButton()
        self.primary_button.setProperty("ofVariant", "primary")
        self.primary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_button.clicked.connect(self.run)
        self.primary_kbd = QLabel("Ctrl+Enter")
        self.primary_kbd.setObjectName("PrimaryKbd")
        kbd_layout = QHBoxLayout(self.primary_button)
        kbd_layout.setContentsMargins(0, 0, 12, 0)
        kbd_layout.addStretch()
        kbd_layout.addWidget(self.primary_kbd)
        # Vazio: o motivo logo acima do botão desabilitado.
        self.empty_caption = QLabel(tr("Abra um PDF para continuar."))
        self.empty_caption.setProperty("ofRole", "help")
        self.empty_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_caption.setWordWrap(True)
        ready_layout = self._footer_layout(ready)
        self._ready_row = QHBoxLayout()
        self._ready_row.setSpacing(8)
        self._ready_row.addWidget(self.primary_button, 1)
        ready_layout.addWidget(self.empty_caption)
        ready_layout.addLayout(self._ready_row)

        # Ocupado: "Comprimir… 12 de 25" e "48%", a barra de 4 px e "Cancelar".
        busy = QWidget()
        self.busy_title = QLabel()
        self.busy_title.setObjectName("BusyText")
        self.busy_percent = QLabel()
        self.busy_percent.setObjectName("ResultTitle")
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.busy_title, 1)
        head.addWidget(self.busy_percent)
        self.progress = QProgressBar()
        self.progress.setObjectName("TaskProgress")
        self.progress.setTextVisible(False)
        self.cancel_button = QPushButton(tr("Cancelar"))
        self.cancel_button.clicked.connect(self._cancel)
        busy_layout = self._footer_layout(busy)
        busy_layout.addLayout(head)
        busy_layout.addWidget(self.progress)
        busy_layout.addWidget(self.cancel_button)

        # Sucesso e erro: o cartão e, embaixo, "Desfazer" ou "Fechar" e a ação principal.
        result = QWidget()
        self.result_card = ResultCard()
        self.undo_button = QPushButton(f"↶ {tr('Desfazer')}")
        self.undo_button.setProperty("ofVariant", "ghost")
        self.undo_button.clicked.connect(self._undo)
        self.dismiss_button = QPushButton(tr("Fechar"))
        self.dismiss_button.setProperty("ofVariant", "ghost")
        self.dismiss_button.clicked.connect(self._back_to_ready)
        self.result_button = QPushButton()
        self.result_button.setProperty("ofVariant", "primary")
        self.result_button.clicked.connect(self._after_result)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.undo_button)
        buttons.addWidget(self.dismiss_button)
        buttons.addWidget(self.result_button, 1)
        result_layout = self._footer_layout(result)
        result_layout.addWidget(self.result_card)
        result_layout.addLayout(buttons)

        for page in (ready, busy, result):
            self.footer.addWidget(page)
        self.footer.currentChanged.connect(self._fit_footer)
        self.footer.currentChanged.connect(self._fade_footer)
        self._fit_footer()
        return self.footer

    def _fade_footer(self, *_args):
        """Troca de estado do rodapé: cross-fade de 160 ms (o efeito sai ao terminar)."""
        if self.footer.isVisible():
            motion.fade_in(self.footer, motion.MEDIUM)

    def _fit_footer(self, *_args):
        """O rodapé tem a altura do estado atual, não a do mais alto (o QStackedWidget usaria
        a maior)."""
        for index in range(self.footer.count()):
            vertical = QSizePolicy.Policy.Preferred if index == self.footer.currentIndex() else QSizePolicy.Policy.Ignored
            self.footer.widget(index).setSizePolicy(QSizePolicy.Policy.Preferred, vertical)
        self.footer.adjustSize()

    def _footer_layout(self, page: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)
        return layout

    def _set_busy_look(self, busy: bool) -> None:
        """Ocupado: o conteúdo fica a 45% e não aceita interação."""
        self.body.setEnabled(not busy)
        if busy:
            effect = QGraphicsOpacityEffect(self.scroll_area)
            effect.setOpacity(0.45)
            self.scroll_area.setGraphicsEffect(effect)
        else:
            self.scroll_area.setGraphicsEffect(None)  # type: ignore[arg-type]

    # -- estados ---------------------------------------------------------------------------

    def state(self) -> str:
        return self._state

    def current_action(self) -> QPushButton | None:
        """O botão de ação do modo visível (o primeiro, se a ferramenta não tem modos)."""
        for button in self._actions:
            parent = button.parentWidget()
            if parent is self.page or parent is None or parent.isVisibleTo(self.page):
                return button
        return None

    def _refresh_ready(self):
        action = self.current_action()
        empty = self._needs_document and not self.session.path()
        if self._state in (READY, EMPTY):
            self._state = EMPTY if empty else READY
        self.primary_button.setVisible(action is not None)
        if action is not None:
            self.primary_button.setText(action.text())
            self.primary_button.setEnabled(action.isEnabled() and not empty)
        self.empty_caption.setVisible(empty and action is not None)
        if self._state in (READY, EMPTY):
            self.footer.setVisible(action is not None)

    def _show_footer(self, index: int):
        self.footer.setCurrentIndex(index)
        self.footer.setVisible(True)

    def run(self) -> bool:
        """A ação principal (o botão do rodapé ou Ctrl+Enter). False se não há o que rodar."""
        action = self.current_action()
        if self._state not in (READY, EMPTY) or action is None or not self.primary_button.isEnabled():
            return False
        action.click()
        return True

    def task_started(self, title: str) -> None:
        self._state = BUSY
        self._busy_label = title
        self.busy_title.setText(f"{title}…")
        self.busy_percent.setText("")
        self.progress.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText(tr("Cancelar"))
        self._set_busy_look(True)
        self._show_footer(1)

    def task_progress(self, done: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.busy_percent.setText(f"{min(100, done * 100 // total)}%")
        step = tr(message) if message else self._busy_label
        if total > 0:
            step = tr("{step}… {current} de {total}").format(step=step, current=min(done + 1, total), total=total)
        else:
            step = f"{step}…"
        self.busy_title.setText(step)

    def task_finished(self, outcome: str) -> None:
        """A operação acabou. Sucesso e erro chegam logo depois, por `show_result`."""
        self._set_busy_look(False)
        self._back_to_ready()
        if outcome == "cancelled":
            self.show_result(INFO, tr("Operação cancelada."), tr("Nada foi gravado."))

    def show_result(self, kind: str, title: str, details: str = "", technical: str = "") -> None:
        self._state = kind
        self.result_card.show_result(kind, title, details, technical)
        self.undo_button.setVisible(kind == SUCCESS and self.session.can_undo())
        self.dismiss_button.setVisible(kind == ERROR)
        self.result_button.setText(tr("Tentar de novo") if kind == ERROR else tr("Concluir"))
        self._show_footer(2)
        window = self.window()
        status_bar = window.statusBar() if hasattr(window, "statusBar") else None
        if status_bar is not None:
            status_bar.showMessage(title, 8000)

    def _back_to_ready(self):
        self._state = READY
        self.footer.setCurrentIndex(0)
        self._refresh_ready()

    def _after_result(self):
        retry = self._state == ERROR
        self._back_to_ready()
        if retry:
            self.run()

    def _undo(self):
        undo = getattr(self.window(), "undo", None)
        if undo is not None:
            undo()
        self._back_to_ready()

    def _cancel(self):
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText(tr("Cancelando..."))
        self._tasks.cancel()


def find_panel(widget: QWidget | None) -> ToolPanel | None:
    while widget is not None:
        if isinstance(widget, ToolPanel):
            return widget
        widget = widget.parentWidget()
    return None


def _split(text: str) -> tuple[str, str]:
    """O resumo (a primeira linha) e o resto, para o cartão de resultado."""
    first, _, rest = text.strip().partition("\n")
    return first, rest.strip()


def notify_success(parent: QWidget, title: str, text: str) -> None:
    """O resultado de uma ferramenta: no cartão do painel dela; fora de um painel, um diálogo."""
    panel = find_panel(parent)
    if panel is None:
        QMessageBox.information(parent, title, text)
        return
    panel.show_result(SUCCESS, *_split(text))


def notify_info(parent: QWidget, title: str, text: str) -> None:
    """Um aviso que não é sucesso nem erro (nada a fazer, nada mudou)."""
    panel = find_panel(parent)
    if panel is None:
        QMessageBox.information(parent, title, text)
        return
    panel.show_result(INFO, *_split(text))


def notify_error(parent: QWidget, title: str, text: str, details: str = "") -> None:
    """Um problema que impede a ferramenta de seguir (falta o arquivo, senha errada...)."""
    panel = find_panel(parent)
    if panel is None:
        QMessageBox.warning(parent, title, text)
        return
    panel.show_result(ERROR, *_split(text), details)
