"""Aba Organizar páginas (A03): grade de miniaturas do documento para reordenar, girar,
excluir, duplicar, inserir páginas em branco e extrair páginas.

A grade ocupa o lugar do visualizador enquanto a ferramenta está aberta (`center_widget`), com
uma barra de botões em cima; o painel lista as alterações pendentes. Elas ficam na grade até
"Aplicar", que as grava no documento de trabalho de uma vez (`ArrangePages`), num passo só de
desfazer. Arrastar uma miniatura a muda de lugar; os botões agem sobre as selecionadas
(Ctrl/Shift+clique seleciona várias).

Cada alteração é uma operação sobre as páginas da grade (girar, apagar, duplicar, inserir em
branco, mover), e a grade é sempre o documento com as operações reaplicadas em ordem. Por isso
dá para desfazer qualquer uma delas sozinha (o "×" na lista) e não só a última. Com a aba
aberta, o Ctrl+Z da janela desfaz primeiro a última alteração da grade (`undo_edit`) e só
depois as versões do documento.
"""

from bisect import bisect_left
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.base import open_pdfium
from core.pages import ArrangePages
from core.progress import PDFIUM_LOCK
from ui import sidebar_icons, theme
from ui.i18n import error_text, tr
from ui.preferences import remember_folder_of, start_folder
from ui.tasks import run_task
from ui.top_bar import bar_separator
from ui.viewer.render import render_page
from ui.viewer.viewer_icons import (
    build_close_icon,
    build_duplicate_icon,
    build_rotate_icon,
    build_rotate_left_icon,
    build_trash_icon,
)

_ROLE = Qt.ItemDataRole.UserRole  # (página de origem a partir de 0, ou None se em branco; giro)
_UID = Qt.ItemDataRole.UserRole + 1  # a identidade da miniatura na grade (sobrevive às operações)
TILE_WIDTH = 128  # a página na grade; a altura é 1,3 vez a largura
TILE_RANGE = (80, 200)  # o controle de tamanho das miniaturas
_RENDER_HEIGHT = 260  # renderiza grande o bastante para o maior tamanho sem borrar


def _tile_height(width: int) -> int:
    return round(width * 1.3)


def _moves(before: list[int], after: list[int]) -> list[tuple[int, int | None]]:
    """As mudanças de lugar que levam a ordem `before` à `after` (as mesmas miniaturas): só as
    que saíram da maior sequência que ficou em ordem, cada uma posta antes da que vem depois
    dela (None: no fim). Aplicadas em ordem, refazem a `after`."""
    position = {uid: index for index, uid in enumerate(before)}
    sequence = [position[uid] for uid in after]
    # Maior subsequência crescente (paciência), para mexer no mínimo de miniaturas.
    tails: list[int] = []
    tail_index: list[int] = []
    parent = [-1] * len(sequence)
    for index, value in enumerate(sequence):
        slot = bisect_left(tails, value)
        if slot == len(tails):
            tails.append(value)
            tail_index.append(index)
        else:
            tails[slot] = value
            tail_index[slot] = index
        parent[index] = tail_index[slot - 1] if slot > 0 else -1
    keep = set()
    index = tail_index[-1] if tail_index else -1
    while index >= 0:
        keep.add(after[index])
        index = parent[index]
    moves = []
    for index in range(len(after) - 1, -1, -1):  # de trás para a frente: o "antes de" já está no lugar
        uid = after[index]
        if uid not in keep:
            moves.append((uid, after[index + 1] if index + 1 < len(after) else None))
    return moves


class _PageTileDelegate(QStyledItemDelegate):
    """A miniatura com sombra, o número embaixo e, selecionada, o contorno no acento e um ✓ no
    canto (para não depender só da cor). Selos no canto: o giro e "Em branco"."""

    def __init__(self, view):
        super().__init__(view)
        self._view = view

    def sizeHint(self, option, index):
        return self._view.gridSize()

    def paint(self, painter: QPainter, option, index):
        t = theme.tokens()
        width = self._view.tile_width
        height = _tile_height(width)
        cell = option.rect
        page = QRect(cell.center().x() - width // 2, cell.top() + 10, width, height)
        source, angle = index.data(_ROLE)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            size = pixmap.deviceIndependentSize().scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF(0, 0, size.width(), size.height())
            target.moveCenter(QPointF(page.center()))
        else:
            target = QRectF(page)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawRoundedRect(target.translated(0, 2).adjusted(-1, 0, 1, 2), 3, 3)  # sombra
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(target)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))

        if selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent"]), 2))
            painter.drawRoundedRect(target.adjusted(-4, -4, 4, 4), 5, 5)
            check = QRectF(target.left() - 8, target.top() - 8, 20, 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["accent"]))
            painter.drawRoundedRect(check, 5, 5)
            pen = QPen(QColor(t["on_accent"]), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            center = check.center()
            painter.drawPolyline([center + QPointF(-4, 0), center + QPointF(-1, 3), center + QPointF(4, -3)])

        badges = []
        if angle:
            badges.append(f"↻ {angle}°")
        if source is None:
            badges.append(tr("Em branco"))
        small = QFont(option.font)
        small.setPixelSize(10)
        painter.setFont(small)
        top = target.top() + 6
        for text in badges:
            badge_width = painter.fontMetrics().horizontalAdvance(text) + 10
            badge = QRectF(target.right() - 6 - badge_width, top, badge_width, 16)
            painter.setPen(QPen(QColor(t["border_strong"]), 1))
            painter.setBrush(QColor(t["panel"]))
            painter.drawRoundedRect(badge, 5, 5)
            painter.setPen(QColor(t["text"]))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
            top += 20

        number = QFont(option.font)
        number.setPixelSize(12)
        number.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
        painter.setFont(number)
        painter.setPen(QColor(t["accent_strong" if selected else "text2"]))
        label = QRect(cell.left(), page.bottom() + 6, cell.width(), 18)
        painter.drawText(label, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, str(index.row() + 1))
        painter.restore()


class OrganizerView(QListWidget):
    """A grade: modo lista que quebra a linha (arrastar reordena as linhas do modelo; o modo
    ícone só mudaria a posição na tela), com o indicador de soltura e a imagem do arrasto
    próprios."""

    shown = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OrganizerView")
        self.tile_width = TILE_WIDTH
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setItemDelegate(_PageTileDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(False)  # o nosso é a barra no acento
        self._drop_bar: QRect | None = None
        self.set_tile_width(TILE_WIDTH)

    def set_tile_width(self, width: int) -> None:
        self.tile_width = width
        self.setGridSize(QSize(width + 34, _tile_height(width) + 40))
        self.doItemsLayout()

    def drop_bar(self) -> QRect | None:
        return self._drop_bar

    def _update_drop_bar(self, position: QPoint) -> None:
        index = self.indexAt(position)
        if index.isValid():
            rect = self.visualRect(index)
            x = rect.left() if position.x() < rect.center().x() else rect.right()
            self._drop_bar = QRect(x - 1, rect.top() + 8, 3, rect.height() - 24)
        elif self.count():
            rect = self.visualRect(self.model().index(self.count() - 1, 0))
            self._drop_bar = QRect(rect.right() - 1, rect.top() + 8, 3, rect.height() - 24)
        self.viewport().update()

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)
        self._update_drop_bar(event.position().toPoint())

    def dragLeaveEvent(self, event):
        super().dragLeaveEvent(event)
        self._drop_bar = None
        self.viewport().update()

    def dropEvent(self, event):
        self._drop_bar = None
        super().dropEvent(event)
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_bar is not None:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.tokens()["accent"]))
            painter.drawRoundedRect(QRectF(self._drop_bar), 2, 2)

    def drag_pixmap(self) -> QPixmap:
        """A miniatura da primeira selecionada, levemente girada, com o número de páginas que
        vão junto."""
        items = self.selectedItems()
        if not items:
            return QPixmap()
        source = items[0].data(Qt.ItemDataRole.DecorationRole)
        width = max(48, self.tile_width // 2)
        height = _tile_height(width)
        image = QPixmap(width + 40, height + 40)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(0.95)
        painter.translate(image.width() / 2, image.height() / 2)
        painter.rotate(-3)
        page = QRectF(-width / 2, -height / 2, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRoundedRect(page.translated(2, 4), 3, 3)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(page)
        if isinstance(source, QPixmap) and not source.isNull():
            painter.drawPixmap(page, source, QRectF(source.rect()))
        painter.resetTransform()
        if len(items) > 1:
            t = theme.tokens()
            badge = QRectF(image.width() - 26, 4, 22, 22)
            painter.setOpacity(1)
            painter.setBrush(QColor(t["accent"]))
            painter.drawEllipse(badge)
            painter.setPen(QColor(t["on_accent"]))
            font = QFont(self.font())
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(len(items)))
        painter.end()
        return image

    def startDrag(self, supported_actions):
        indexes = self.selectedIndexes()
        if not indexes:
            return
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData(indexes))
        pixmap = self.drag_pixmap()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        drag.exec(supported_actions, self.defaultDropAction())
        self._drop_bar = None

    def showEvent(self, event):
        super().showEvent(event)
        self.shown.emit()


def _tool_button(icon: QIcon, text: str) -> QToolButton:
    button = QToolButton()
    button.setIcon(icon)
    button.setText(text)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setProperty("ofRole", "toolbar")
    return button


class OrganizePage(QWidget):
    edits_changed = Signal()  # a grade mudou: desfazer/refazer da grade podem ter mudado
    edit_label = "edição na grade"  # o "Desfazer edição na grade" do menu

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self._document = None
        self._pixmaps: dict[int, QPixmap] = {}
        self._pending: set[int] = set()
        self._base: list[tuple[int, int | None, int]] = []  # (identidade, página, giro) do documento
        self._ops: list[tuple[str, object, str]] = []  # (tipo, dados, descrição), em ordem
        self._redo: list[tuple[str, object, str]] = []
        self._next_uid = 0
        self._last_order: list[int] = []
        self._rebuilding = False

        # A grade e a barra dela: no lugar do visualizador, com a ferramenta aberta.
        self.grid = OrganizerView()
        self.grid.itemSelectionChanged.connect(self._update_buttons)
        self.grid.model().rowsMoved.connect(self._on_rows_moved)
        self.grid.shown.connect(self._start_rendering)
        delete_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.grid)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self.delete_selected)

        self.selection_badge = QLabel()
        self.selection_badge.setObjectName("SelectionBadge")
        self.rotate_left_button = _tool_button(build_rotate_left_icon(), tr("Girar à esquerda"))
        self.rotate_left_button.clicked.connect(lambda: self.rotate_selected(270))
        self.rotate_right_button = _tool_button(build_rotate_icon(), tr("Girar à direita"))
        self.rotate_right_button.clicked.connect(lambda: self.rotate_selected(90))
        self.duplicate_button = _tool_button(build_duplicate_icon(), tr("Duplicar"))
        self.duplicate_button.clicked.connect(self.duplicate_selected)
        self.blank_button = _tool_button(sidebar_icons.build_create_icon(), tr("Em branco"))
        self.blank_button.setToolTip(tr("Insere uma página em branco depois da última selecionada, ou no fim."))
        self.blank_button.clicked.connect(self.insert_blank)
        self.delete_button = _tool_button(build_trash_icon(), tr("Apagar"))
        self.delete_button.setToolTip(tr("Apaga as páginas selecionadas (Delete)"))
        self.delete_button.clicked.connect(self.delete_selected)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setFixedWidth(96)
        self.size_slider.setRange(*TILE_RANGE)
        self.size_slider.setValue(TILE_WIDTH)
        self.size_slider.setToolTip(tr("Tamanho das miniaturas"))
        self.size_slider.setAccessibleName(tr("Tamanho das miniaturas"))
        self.size_slider.valueChanged.connect(self.grid.set_tile_width)
        toolbar = QWidget()
        toolbar.setObjectName("OrganizerToolbar")
        toolbar.setFixedHeight(48)
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(12, 0, 12, 0)
        bar.setSpacing(4)
        bar.addWidget(self.selection_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        bar.addSpacing(4)
        bar.addWidget(bar_separator())
        bar.addSpacing(4)
        for button in (
            self.rotate_left_button,
            self.rotate_right_button,
            self.duplicate_button,
            self.blank_button,
            self.delete_button,
        ):
            bar.addWidget(button)
        bar.addStretch()
        bar.addWidget(self.size_slider)
        self.center_widget = QWidget()
        self.center_widget.setObjectName("OrganizerArea")
        center = QVBoxLayout(self.center_widget)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        center.addWidget(toolbar)
        center.addWidget(self.grid, 1)

        # Painel: as alterações pendentes (uma seção própria), as opções e o rodapé.
        self.changes_title = QLabel()
        self.changes_title.setObjectName("ChangesTitle")
        self.changes_title.setProperty("ofRole", "section")
        self.changes_list = QListWidget()
        self.changes_list.setObjectName("ChangesList")
        self.changes_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.changes_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.changes_empty = QLabel(tr("Nenhuma alteração ainda."))
        self.changes_empty.setProperty("ofRole", "secondary")
        changes = QWidget()
        changes_layout = QVBoxLayout(changes)
        changes_layout.setContentsMargins(0, 0, 0, 0)
        changes_layout.addWidget(self.changes_list)
        changes_layout.addWidget(self.changes_empty)
        self.extra_section = (self.changes_title, changes)

        self.move_back_button = QPushButton(tr("Mover para trás"))
        self.move_back_button.clicked.connect(lambda: self.move_selected(-1))
        self.move_forward_button = QPushButton(tr("Mover para a frente"))
        self.move_forward_button.clicked.connect(lambda: self.move_selected(1))
        self.extract_button = QPushButton(tr("Extrair..."))
        self.extract_button.setToolTip(tr("Salva as páginas selecionadas em outro arquivo."))
        self.extract_button.clicked.connect(self._extract)
        self._selection_buttons = [
            self.rotate_left_button,
            self.rotate_right_button,
            self.move_back_button,
            self.move_forward_button,
            self.duplicate_button,
            self.delete_button,
            self.extract_button,
        ]

        self.apply_button = QPushButton()
        self.action_buttons.append(self.apply_button)
        self.apply_button.clicked.connect(self._apply)
        self.discard_button = QPushButton(tr("Descartar"))
        self.discard_button.setToolTip(tr("Volta a grade para o documento como está"))
        self.discard_button.clicked.connect(self._load)
        self.footer_buttons = [self.discard_button]

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        hint = QLabel(
            tr(
                "Arraste as miniaturas para mudar a ordem; Ctrl ou Shift + clique seleciona várias. "
                "Nada muda no documento até Aplicar."
            )
        )
        hint.setWordWrap(True)
        hint.setProperty("ofRole", "secondary")
        moves = QHBoxLayout()
        moves.addWidget(self.move_back_button)
        moves.addWidget(self.move_forward_button)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(moves)
        layout.addWidget(self.extract_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.discard_button)
        layout.addWidget(self.apply_button)

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_next)

        session.path_changed.connect(self._load)
        self._load()

    # -- estado da grade --------------------------------------------------------------

    def layout_items(self) -> list[tuple[int | None, int]]:
        """As páginas na ordem da grade, como `ArrangePages` as recebe."""
        return [tuple(self.grid.item(row).data(_ROLE)) for row in range(self.grid.count())]

    def _original(self) -> list[tuple[int | None, int]]:
        return [(source, angle) for _uid, source, angle in self._base]

    def is_modified(self) -> bool:
        return self.layout_items() != self._original()

    def changes(self) -> list[str]:
        """A descrição de cada alteração pendente, em ordem."""
        return [description for _kind, _data, description in self._ops]

    def _order(self) -> list[int]:
        return [self.grid.item(row).data(_UID) for row in range(self.grid.count())]

    def _selected_rows(self) -> list[int]:
        return sorted(self.grid.row(item) for item in self.grid.selectedItems())

    def _selected_uids(self) -> list[int]:
        return [self.grid.item(row).data(_UID) for row in self._selected_rows()]

    def _select_rows(self, rows) -> None:
        self.grid.clearSelection()
        for row in rows:
            self.grid.item(row).setSelected(True)
        if rows:
            self.grid.setCurrentRow(rows[-1], QItemSelectionModel.SelectionFlag.NoUpdate)

    def _update_buttons(self, *_args) -> None:
        selected = len(self.grid.selectedItems())
        for button in self._selection_buttons:
            button.setEnabled(bool(selected))
        self.blank_button.setEnabled(self._document is not None)
        self.selection_badge.setText(tr("{count} selecionadas").format(count=selected))
        modified = self.is_modified()
        count = len(self._ops)
        self.apply_button.setText(tr("Aplicar {count} alterações").format(count=count) if count else tr("Aplicar"))
        self.apply_button.setEnabled(modified and self.grid.count() > 0)
        self.discard_button.setEnabled(bool(self._ops))

    # -- documento --------------------------------------------------------------------

    def _load(self) -> None:
        """Mostra o documento de trabalho como ele está (sem as mudanças não aplicadas)."""
        self._timer.stop()
        self._pixmaps = {}
        self._pending = set()
        self.status_label.clear()
        total = 0
        with PDFIUM_LOCK:
            if self._document is not None:
                self._document.close()
                self._document = None
            path = self.session.path()
            if path:
                try:
                    self._document = open_pdfium(path)
                    total = len(self._document)
                except Exception as exc:
                    self._document = None
                    self.status_label.setText(error_text(exc))
        self._base = [(index, index, 0) for index in range(total)]
        self._next_uid = total
        self._ops, self._redo = [], []
        self._pending = set(range(total))
        self._rebuild([])
        self._start_rendering()

    def _start_rendering(self) -> None:
        if self._pending and self.grid.isVisible():
            self._timer.start()

    def render_all(self) -> None:
        """Renderiza o que falta de uma vez (usado nos testes)."""
        while self._pending:
            self._render_page(min(self._pending))

    def _render_next(self) -> None:
        # Só enquanto a grade está à vista: escondida, cada versão nova do documento
        # renderizaria todas as miniaturas à toa.
        if self._document is None or not self._pending or not self.grid.isVisible():
            self._timer.stop()
            return
        first = self.grid.indexAt(QPoint(10, 10)).row()
        visible = (self.grid.item(row).data(_ROLE)[0] for row in range(max(first, 0), self.grid.count()))
        index = next((index for index in visible if index in self._pending), min(self._pending))
        self._render_page(index)

    def _render_page(self, index: int) -> None:
        self._pending.discard(index)
        with PDFIUM_LOCK:
            page = self._document[index]
            # Pelo lado maior: girada ou não, a página ocupa a altura do quadro.
            longest = max(page.get_size())
            scale = _RENDER_HEIGHT / longest if longest > 0 else 0.2
            self._pixmaps[index] = render_page(page, scale, self.devicePixelRatioF())
            page.close()
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            if item.data(_ROLE)[0] == index:
                self._refresh_pixmap(item)

    def _refresh_pixmap(self, item: QListWidgetItem) -> None:
        index, angle = item.data(_ROLE)
        pixmap = self._pixmaps.get(index) if index is not None else None
        if pixmap is not None and angle:
            ratio = pixmap.devicePixelRatio()
            pixmap = pixmap.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            pixmap.setDevicePixelRatio(ratio)
        item.setData(Qt.ItemDataRole.DecorationRole, pixmap)

    # -- operações ----------------------------------------------------------------------

    def _replay(self, ops) -> list[tuple[int, int | None, int]]:
        """O documento com as operações aplicadas em ordem. Uma operação sobre uma miniatura
        que não existe mais (desfeita a que a criou) é ignorada naquele ponto."""
        items = list(self._base)
        for kind, data, _description in ops:
            if kind == "rotate":
                uids, delta = data
                items = [(uid, source, (angle + delta) % 360 if uid in uids else angle) for uid, source, angle in items]
            elif kind == "delete":
                items = [item for item in items if item[0] not in data]
            elif kind == "duplicate":
                for source_uid, new_uid in data:
                    at = next((n for n, item in enumerate(items) if item[0] == source_uid), None)
                    if at is not None:
                        items.insert(at + 1, (new_uid, items[at][1], items[at][2]))
            elif kind == "blank":
                new_uid, after = data
                at = next((n for n, item in enumerate(items) if item[0] == after), None)
                items.insert(len(items) if at is None else at + 1, (new_uid, None, 0))
            elif kind == "move":
                for uid, before in data:
                    at = next((n for n, item in enumerate(items) if item[0] == uid), None)
                    if at is None:
                        continue
                    moved = items.pop(at)
                    target = next((n for n, item in enumerate(items) if item[0] == before), len(items))
                    items.insert(target, moved)
        return items

    def _rebuild(self, selected_uids) -> None:
        """Refaz a grade a partir das operações e seleciona `selected_uids`."""
        self._rebuilding = True
        self.grid.clear()
        rows = []
        for uid, source, angle in self._replay(self._ops):
            item = QListWidgetItem()
            item.setData(_ROLE, (source, angle))
            item.setData(_UID, uid)
            label = tr("Página em branco") if source is None else tr("Página {number}").format(number=source + 1)
            item.setText(label)
            item.setToolTip(label)
            self._refresh_pixmap(item)
            self.grid.addItem(item)
            if uid in selected_uids:
                rows.append(self.grid.count() - 1)
        self._rebuilding = False
        self._select_rows(rows)
        self._last_order = self._order()
        self._refresh_changes()

    def _add(self, kind: str, data, description: str, selected_uids) -> None:
        self._ops.append((kind, data, description))
        self._redo.clear()
        self._rebuild(selected_uids)

    def remove_change(self, position: int) -> None:
        """O "×" de uma alteração da lista: só ela sai; as outras continuam."""
        if 0 <= position < len(self._ops):
            self._ops.pop(position)
            self._redo.clear()
            self._rebuild(self._selected_uids())

    def _refresh_changes(self) -> None:
        self.changes_list.clear()
        icons = {
            "rotate": build_rotate_icon,
            "delete": build_trash_icon,
            "duplicate": build_duplicate_icon,
            "blank": sidebar_icons.build_create_icon,
            "move": sidebar_icons.build_organize_icon,
        }
        for position, (kind, _data, description) in enumerate(self._ops):
            item = QListWidgetItem()
            row = QWidget()
            row.setObjectName("ChangeRow")
            icon = QLabel()
            icon.setPixmap(icons[kind]().pixmap(QSize(16, 16)))
            text = QLabel(description)
            text.setWordWrap(True)
            undo = QToolButton()
            undo.setIcon(build_close_icon())
            undo.setProperty("ofRole", "icon")
            undo.setToolTip(tr("Desfazer só esta alteração"))
            undo.setAccessibleName(tr("Desfazer: {change}").format(change=description))
            undo.clicked.connect(lambda _checked=False, p=position: self.remove_change(p))
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 4, 4, 4)
            layout.setSpacing(8)
            layout.addWidget(icon)
            layout.addWidget(text, 1)
            layout.addWidget(undo)
            item.setSizeHint(QSize(0, 40))
            self.changes_list.addItem(item)
            self.changes_list.setItemWidget(item, row)
        self.changes_title.setText(tr("Alterações pendentes · {count}").format(count=len(self._ops)).upper())
        self.changes_list.setVisible(bool(self._ops))
        self.changes_list.setFixedHeight(min(6, max(1, len(self._ops))) * 42 + 4)
        self.changes_empty.setVisible(not self._ops)
        self._update_buttons()
        self.edits_changed.emit()

    def _pages_text(self, uids) -> str:
        """"a página 3", "a página em branco" ou "4 páginas" (pela página de origem)."""
        sources = {uid: source for uid, source, _angle in self._replay(self._ops)}
        if len(uids) != 1:
            return tr("{count} páginas").format(count=len(uids))
        source = sources.get(uids[0])
        return tr("a página em branco") if source is None else tr("a página {number}").format(number=source + 1)

    # -- desfazer na grade --------------------------------------------------------------

    def _on_rows_moved(self, *_args) -> None:
        """Arrastar: a nova ordem vira uma operação de mover."""
        if self._rebuilding:
            return
        order = self._order()
        moves = _moves(self._last_order, order)
        if not moves:
            return
        self._ops.append(("move", moves, tr("Moveu {pages}").format(pages=self._pages_text([uid for uid, _ in moves]))))
        self._redo.clear()
        self._last_order = order
        self._refresh_changes()

    def can_undo_edit(self) -> bool:
        return bool(self._ops)

    def can_redo_edit(self) -> bool:
        return bool(self._redo)

    def undo_edit(self) -> None:
        if self._ops:
            self._redo.append(self._ops.pop())
            self._rebuild(self._selected_uids())

    def redo_edit(self) -> None:
        if self._redo:
            self._ops.append(self._redo.pop())
            self._rebuild(self._selected_uids())

    # -- edição -----------------------------------------------------------------------

    def rotate_selected(self, delta: int) -> None:
        uids = self._selected_uids()
        if not uids:
            return
        text = tr("Girou {pages} à direita") if delta == 90 else tr("Girou {pages} à esquerda")
        self._add("rotate", (frozenset(uids), delta), text.format(pages=self._pages_text(uids)), uids)

    def move_selected(self, step: int) -> None:
        rows = self._selected_rows()
        if not rows or (step < 0 and rows[0] == 0) or (step > 0 and rows[-1] == self.grid.count() - 1):
            return
        order = self._order()
        uids = [order[row] for row in rows]
        for row in rows if step < 0 else reversed(rows):
            order.insert(row + step, order.pop(row))
        moves = _moves(self._order(), order)
        self._add("move", moves, tr("Moveu {pages}").format(pages=self._pages_text(uids)), uids)

    def duplicate_selected(self) -> None:
        uids = self._selected_uids()
        if not uids:
            return
        pairs = []
        for uid in uids:
            pairs.append((uid, self._next_uid))
            self._next_uid += 1
        text = tr("Duplicou {pages}").format(pages=self._pages_text(uids))
        self._add("duplicate", pairs, text, [new for _uid, new in pairs])  # a cópia fica selecionada

    def delete_selected(self) -> None:
        uids = self._selected_uids()
        if not uids:
            return
        self._add("delete", frozenset(uids), tr("Apagou {pages}").format(pages=self._pages_text(uids)), [])

    def insert_blank(self) -> None:
        if self._document is None:
            return
        uids = self._selected_uids()
        new_uid = self._next_uid
        self._next_uid += 1
        self._add("blank", (new_uid, uids[-1] if uids else None), tr("Inseriu uma página em branco"), [new_uid])

    # -- gravar -----------------------------------------------------------------------

    def _apply(self) -> None:
        input_path = self.session.path()
        layout = self.layout_items()
        if not input_path or not layout or not self.is_modified():
            return
        output_path = self.session.new_version_path()
        run_task(
            self,
            tr("Organizar páginas"),
            lambda _progress: ArrangePages().run(input_path, output_path, layout),
            on_success=lambda _result: self.session.open(output_path),
        )

    def _extract(self) -> None:
        input_path = self.session.path()
        rows = self._selected_rows()
        if not input_path or not rows:
            return
        layout = [tuple(self.grid.item(row).data(_ROLE)) for row in rows]
        stem = Path(self.session.source_path() or input_path).stem
        target, _ = QFileDialog.getSaveFileName(
            self, tr("Extrair páginas"), str(Path(start_folder()) / f"{stem}_paginas.pdf"), "PDF (*.pdf)"
        )
        if target:
            self.extract_to(target, layout)

    def extract_to(self, target: str, layout: list[tuple[int | None, int]]) -> bool:
        remember_folder_of(target)
        input_path = self.session.path()
        return run_task(
            self,
            tr("Extrair páginas"),
            lambda _progress: ArrangePages().run(input_path, target, layout),
            on_success=lambda _result: self.status_label.setText(
                tr("{count} página(s) salva(s) em {path}.").format(count=len(layout), path=target)
            ),
        )
