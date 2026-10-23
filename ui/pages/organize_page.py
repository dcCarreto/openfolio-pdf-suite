"""Aba Organizar páginas (A03): grade de miniaturas do documento para reordenar, girar,
excluir, duplicar, inserir páginas em branco e extrair páginas.

As mudanças ficam na grade até "Aplicar", que as grava no documento de trabalho de uma vez
(`ArrangePages`), num passo só de desfazer. Arrastar uma miniatura a muda de lugar; os
botões agem sobre as miniaturas selecionadas (Ctrl/Shift+clique seleciona várias).

Antes de aplicar, cada mudança na grade também se desfaz: com esta aba aberta, o Ctrl+Z
da janela desfaz primeiro as mudanças da grade (`undo_edit`) e só depois as versões do
documento.
"""

from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from core.base import open_pdfium
from core.pages import ArrangePages
from core.progress import PDFIUM_LOCK
from ui.i18n import error_text, tr
from ui.preferences import remember_folder_of, start_folder
from ui.tasks import run_task
from ui.viewer.render import framed, render_page

_ICON_SIZE = QSize(96, 128)
_ROLE = Qt.ItemDataRole.UserRole  # (página de origem a partir de 0, ou None se em branco; giro)


class _CaptionBelowDelegate(QStyledItemDelegate):
    """Legenda abaixo da miniatura. A grade fica no modo lista (que reordena as linhas ao
    arrastar; o modo ícone só mudaria a posição na tela), e o modo lista põe a legenda ao lado."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Position.Top
        option.displayAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop


class OrganizePage(QWidget):
    edits_changed = Signal()  # a grade mudou: desfazer/refazer da grade podem ter mudado

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._document = None
        self._pixmaps: dict[int, QPixmap] = {}
        self._pending: set[int] = set()
        self._original: list[tuple[int | None, int]] = []
        self._last_layout: list[tuple[int | None, int]] = []
        self._undo_stack: list[list[tuple[int | None, int]]] = []
        self._redo_stack: list[list[tuple[int | None, int]]] = []
        self._blank = QPixmap(_ICON_SIZE.width(), _ICON_SIZE.width() * 4 // 3)
        self._blank.fill(QColor("white"))
        self._blank = framed(self._blank)

        self.grid = QListWidget()
        self.grid.setFlow(QListView.Flow.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setUniformItemSizes(True)
        self.grid.setIconSize(_ICON_SIZE)
        self.grid.setGridSize(QSize(120, 156))
        self.grid.setItemDelegate(_CaptionBelowDelegate(self.grid))
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.grid.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.grid.setMinimumHeight(320)
        self.grid.itemSelectionChanged.connect(self._update_buttons)
        self.grid.model().rowsMoved.connect(self._changed)
        delete_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.grid)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self.delete_selected)

        self.rotate_left_button = QPushButton(tr("Girar à esquerda"))
        self.rotate_left_button.clicked.connect(lambda: self.rotate_selected(270))
        self.rotate_right_button = QPushButton(tr("Girar à direita"))
        self.rotate_right_button.clicked.connect(lambda: self.rotate_selected(90))
        self.move_back_button = QPushButton(tr("Mover para trás"))
        self.move_back_button.clicked.connect(lambda: self.move_selected(-1))
        self.move_forward_button = QPushButton(tr("Mover para a frente"))
        self.move_forward_button.clicked.connect(lambda: self.move_selected(1))
        self.duplicate_button = QPushButton(tr("Duplicar"))
        self.duplicate_button.clicked.connect(self.duplicate_selected)
        self.delete_button = QPushButton(tr("Excluir"))
        self.delete_button.clicked.connect(self.delete_selected)
        self.blank_button = QPushButton(tr("Página em branco"))
        self.blank_button.setToolTip(tr("Insere uma página em branco depois da última selecionada, ou no fim."))
        self.blank_button.clicked.connect(self.insert_blank)
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

        self.apply_button = QPushButton(tr("Aplicar"))
        self.apply_button.clicked.connect(self._apply)
        self.discard_button = QPushButton(tr("Descartar alterações"))
        self.discard_button.clicked.connect(self._load)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        buttons = QGridLayout()
        for position, button in enumerate(
            [
                self.rotate_left_button,
                self.rotate_right_button,
                self.move_back_button,
                self.move_forward_button,
                self.duplicate_button,
                self.delete_button,
                self.blank_button,
                self.extract_button,
            ]
        ):
            buttons.addWidget(button, position // 2, position % 2)
        actions = QGridLayout()
        actions.addWidget(self.discard_button, 0, 0)
        actions.addWidget(self.apply_button, 0, 1)

        hint = QLabel(tr("Arraste as miniaturas para mudar a ordem; Ctrl ou Shift + clique seleciona várias."))
        hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.grid, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addLayout(actions)

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_next)

        session.path_changed.connect(self._load)
        self._load()

    # -- estado da grade --------------------------------------------------------------

    def layout_items(self) -> list[tuple[int | None, int]]:
        """As páginas na ordem da grade, como `ArrangePages` as recebe."""
        return [tuple(self.grid.item(row).data(_ROLE)) for row in range(self.grid.count())]

    def is_modified(self) -> bool:
        return self.layout_items() != self._original

    def _selected_rows(self) -> list[int]:
        return sorted(self.grid.row(item) for item in self.grid.selectedItems())

    def _select_rows(self, rows) -> None:
        self.grid.clearSelection()
        for row in rows:
            self.grid.item(row).setSelected(True)
        if rows:
            self.grid.setCurrentRow(rows[-1], QItemSelectionModel.SelectionFlag.NoUpdate)

    def _update_buttons(self, *_args) -> None:
        has_selection = bool(self.grid.selectedItems())
        for button in self._selection_buttons:
            button.setEnabled(has_selection)
        self.blank_button.setEnabled(self._document is not None)
        modified = self.is_modified()
        self.apply_button.setEnabled(modified and self.grid.count() > 0)
        self.discard_button.setEnabled(modified)

    # -- documento --------------------------------------------------------------------

    def _load(self) -> None:
        """Mostra o documento de trabalho como ele está (sem as mudanças não aplicadas)."""
        self._timer.stop()
        self.grid.clear()
        self._pixmaps = {}
        self._pending = set()
        self.status_label.clear()
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
        if self._document is not None:
            for index in range(total):
                self.grid.addItem(self._new_item(index))
            self._pending = set(range(total))
            if self.isVisible():
                self._timer.start()
        self._original = self._last_layout = self.layout_items()
        self._undo_stack, self._redo_stack = [], []
        self._update_buttons()
        self.edits_changed.emit()

    def _new_item(self, index: int | None, angle: int = 0) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(_ROLE, (index, angle))
        if index is None:
            item.setText(tr("Página em branco"))
        else:
            item.setText(tr("Página {number}").format(number=index + 1))
        self._refresh_icon(item)
        return item

    def _refresh_icon(self, item: QListWidgetItem) -> None:
        index, angle = item.data(_ROLE)
        pixmap = self._blank if index is None else self._pixmaps.get(index, self._blank)
        if angle:
            ratio = pixmap.devicePixelRatio()
            pixmap = pixmap.transformed(QTransform().rotate(angle))
            pixmap.setDevicePixelRatio(ratio)
        item.setIcon(QIcon(pixmap))

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._timer.start()

    def render_all(self) -> None:
        """Renderiza o que falta de uma vez (usado nos testes)."""
        while self._pending:
            self._render_page(min(self._pending))

    def _render_next(self) -> None:
        # Só enquanto a aba está à vista: escondida, cada versão nova do documento
        # renderizaria todas as miniaturas à toa.
        if self._document is None or not self._pending or not self.isVisible():
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
            # Pelo lado maior: girada ou não, a página ocupa a altura do ícone.
            longest = max(page.get_size())
            scale = _ICON_SIZE.height() / longest if longest > 0 else 0.2
            self._pixmaps[index] = framed(render_page(page, scale, self.devicePixelRatioF()))
            page.close()
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            if item.data(_ROLE)[0] == index:
                self._refresh_icon(item)

    # -- desfazer na grade --------------------------------------------------------------

    def _changed(self, *_args) -> None:
        """Depois de cada mudança na grade (botões ou arrastar): guarda o estado anterior."""
        layout = self.layout_items()
        if layout != self._last_layout:
            self._undo_stack.append(self._last_layout)
            self._redo_stack.clear()
            self._last_layout = layout
        self._update_buttons()
        self.edits_changed.emit()

    def can_undo_edit(self) -> bool:
        return bool(self._undo_stack)

    def can_redo_edit(self) -> bool:
        return bool(self._redo_stack)

    def undo_edit(self) -> None:
        if self._undo_stack:
            self._redo_stack.append(self._last_layout)
            self._restore(self._undo_stack.pop())

    def redo_edit(self) -> None:
        if self._redo_stack:
            self._undo_stack.append(self._last_layout)
            self._restore(self._redo_stack.pop())

    def _restore(self, layout: list[tuple[int | None, int]]) -> None:
        self.grid.clear()
        for index, angle in layout:
            self.grid.addItem(self._new_item(index, angle))
        self._last_layout = layout
        self._update_buttons()
        self.edits_changed.emit()

    # -- edição -----------------------------------------------------------------------

    def rotate_selected(self, delta: int) -> None:
        for item in self.grid.selectedItems():
            index, angle = item.data(_ROLE)
            item.setData(_ROLE, (index, (angle + delta) % 360))
            self._refresh_icon(item)
        self._changed()

    def move_selected(self, step: int) -> None:
        rows = self._selected_rows()
        if not rows or (step < 0 and rows[0] == 0) or (step > 0 and rows[-1] == self.grid.count() - 1):
            return
        for row in rows if step < 0 else reversed(rows):
            self.grid.insertItem(row + step, self.grid.takeItem(row))
        self._select_rows([row + step for row in rows])
        self._changed()

    def duplicate_selected(self) -> None:
        rows = self._selected_rows()
        for row in reversed(rows):
            index, angle = self.grid.item(row).data(_ROLE)
            self.grid.insertItem(row + 1, self._new_item(index, angle))
        self._select_rows([row + position + 1 for position, row in enumerate(rows)])
        self._changed()

    def delete_selected(self) -> None:
        for row in reversed(self._selected_rows()):
            self.grid.takeItem(row)
        self.grid.clearSelection()
        self._changed()

    def insert_blank(self) -> None:
        if self._document is None:
            return
        rows = self._selected_rows()
        row = rows[-1] + 1 if rows else self.grid.count()
        self.grid.insertItem(row, self._new_item(None))
        self._select_rows([row])
        self._changed()

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
