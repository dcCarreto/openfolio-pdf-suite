"""Aba de marcadores (sumário/outline) de PDFs."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.base import READ, open_reader
from core.bookmarks import DetectHeadings, ListOutline, OutlineItem, SetOutline
from ui.i18n import tr
from ui.tasks import call_with_progress, run_task
from ui.widgets.current_page import with_current_page_button
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_TITLE, _PAGE = 0, 1
_ITEM_FLAGS = (
    Qt.ItemFlag.ItemIsSelectable
    | Qt.ItemFlag.ItemIsEnabled
    | Qt.ItemFlag.ItemIsEditable
    | Qt.ItemFlag.ItemIsDragEnabled
    | Qt.ItemFlag.ItemIsDropEnabled
)


class BookmarksPage(QWidget):
    """Edita o sumário (marcadores de navegação) de um PDF: começa pelos marcadores que ele
    já tem, que podem ser renomeados, reordenados e aninhados (arrastando ou pelos botões),
    e pode ser gerado a partir dos títulos do documento."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="com_marcadores"
        )

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("Título"), tr("Página")])
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setToolTip(
            tr("Arraste para reordenar ou solte sobre outro marcador para aninhar. Duplo clique edita o título ou a página.")
        )

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(tr("Título do marcador"))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 9999)

        add_button = QPushButton(tr("Adicionar"))
        add_button.clicked.connect(self._add_bookmark)
        page_row = QHBoxLayout()
        page_row.addWidget(QLabel(tr("Página:")))
        page_row.addLayout(with_current_page_button(self.page_spin, session), 1)
        page_row.addWidget(add_button)

        move_row = QHBoxLayout()
        for label, tip, action in (
            ("Subir", "Move o marcador para cima, entre os do mesmo nível.", lambda: self._move(-1)),
            ("Descer", "Move o marcador para baixo, entre os do mesmo nível.", lambda: self._move(1)),
            ("Para dentro", "Põe o marcador dentro do que está acima dele.", self._indent),
            ("Para fora", "Tira o marcador de dentro do marcador pai.", self._outdent),
            ("Remover", "Remove o marcador e os que estão dentro dele.", self._remove_selected),
        ):
            button = QPushButton(tr(label))
            button.setToolTip(tr(tip))
            button.clicked.connect(action)
            move_row.addWidget(button)

        reload_button = QPushButton(tr("Recarregar do documento"))
        reload_button.setToolTip(tr("Descarta as mudanças e volta aos marcadores do documento aberto."))
        reload_button.clicked.connect(self._load_from_document)
        detect_button = QPushButton(tr("Gerar a partir dos títulos"))
        detect_button.setToolTip(
            tr("Sugere um sumário com as linhas em fonte maior que a do texto; cada tamanho vira um nível.")
        )
        detect_button.clicked.connect(self._detect_headings)
        source_row = QHBoxLayout()
        source_row.addWidget(reload_button)
        source_row.addWidget(detect_button)

        save_button = QPushButton(tr("Salvar"))
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Marcadores:")))
        layout.addWidget(self.tree)
        layout.addLayout(move_row)
        layout.addLayout(source_row)
        layout.addWidget(self.title_edit)
        layout.addLayout(page_row)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(save_button)

        session.path_changed.connect(self._load_from_document)
        self._load_from_document()

    # --- Árvore ------------------------------------------------------------------------

    def _new_item(self, title: str, page_index: int | None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title, "" if page_index is None else str(page_index + 1)])
        item.setFlags(_ITEM_FLAGS)
        return item

    def set_items(self, items: list[OutlineItem]) -> None:
        self.tree.clear()
        parents: list[QTreeWidgetItem] = []
        for entry in items:
            item = self._new_item(entry.title, entry.page_index)
            del parents[entry.level :]
            (parents[-1].addChild if parents else self.tree.addTopLevelItem)(item)
            parents.append(item)
        self.tree.expandAll()

    def items(self) -> list[tuple[int, str, str]]:
        """(nível, título, página digitada) de cada marcador, na ordem da árvore."""
        result: list[tuple[int, str, str]] = []

        def walk(item: QTreeWidgetItem | None, level: int) -> None:
            if item is None:
                return
            if level >= 0:  # a raiz invisível da árvore não é um marcador
                result.append((level, item.text(_TITLE), item.text(_PAGE)))
            for index in range(item.childCount()):
                walk(item.child(index), level + 1)

        walk(self.tree.invisibleRootItem(), -1)
        return result

    def _load_from_document(self):
        path = self.session.path()
        try:
            self.set_items(ListOutline().run(path) if path else [])
        except Exception:
            self.set_items([])  # sem sumário legível: começa do zero

    def _selected(self) -> QTreeWidgetItem | None:
        items = self.tree.selectedItems()
        return items[0] if items else None

    def _parent_of(self, item: QTreeWidgetItem) -> QTreeWidgetItem:
        return item.parent() or self.tree.invisibleRootItem()

    def _place(self, item: QTreeWidgetItem, parent: QTreeWidgetItem, index: int) -> None:
        parent.insertChild(index, item)
        item.setExpanded(True)
        self.tree.setCurrentItem(item)

    def _move(self, step: int):
        item = self._selected()
        if item is None:
            return
        parent = self._parent_of(item)
        index = parent.indexOfChild(item) + step
        if 0 <= index < parent.childCount():
            parent.takeChild(parent.indexOfChild(item))
            self._place(item, parent, index)

    def _indent(self):
        item = self._selected()
        if item is None:
            return
        parent = self._parent_of(item)
        index = parent.indexOfChild(item)
        if index > 0:
            new_parent = parent.child(index - 1)
            parent.takeChild(index)
            self._place(item, new_parent, new_parent.childCount())
            new_parent.setExpanded(True)

    def _outdent(self):
        item = self._selected()
        if item is None or item.parent() is None:
            return
        parent = item.parent()
        grandparent = self._parent_of(parent)
        parent.takeChild(parent.indexOfChild(item))
        self._place(item, grandparent, grandparent.indexOfChild(parent) + 1)

    def _remove_selected(self):
        item = self._selected()
        if item is not None:
            parent = self._parent_of(item)
            parent.takeChild(parent.indexOfChild(item))

    def _add_bookmark(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, tr("Marcadores"), tr("Digite um título para o marcador."))
            return
        item = self._new_item(title, self.page_spin.value() - 1)  # o core conta a partir de 0
        self.tree.addTopLevelItem(item)
        self.tree.setCurrentItem(item)
        self.title_edit.clear()

    def _detect_headings(self):
        input_path = self.session.path()
        if not input_path:
            QMessageBox.warning(self, tr("Marcadores"), tr("Abra um PDF para começar."))
            return

        def done(items):
            if not items:
                QMessageBox.information(
                    self, tr("Marcadores"), tr("Nenhum título encontrado: o texto todo tem o mesmo tamanho.")
                )
                return
            replace = QMessageBox.StandardButton.Yes
            if self.tree.topLevelItemCount() and (
                QMessageBox.question(
                    self,
                    tr("Marcadores"),
                    tr("Trocar os marcadores da lista pelos {count} títulos encontrados?").format(count=len(items)),
                )
                != replace
            ):
                return
            self.set_items(items)

        run_task(
            self,
            tr("Marcadores"),
            call_with_progress(DetectHeadings().run, input_path),
            on_success=done,
            error_message=tr("Falha ao procurar os títulos: {error}"),
        )

    def _save(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Marcadores"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Marcadores"), tr("Escolha o arquivo de saída."))
            return

        rows = self.items()
        if any(not title.strip() for _level, title, _page in rows):
            QMessageBox.warning(self, tr("Marcadores"), tr("Há um marcador sem título."))
            return

        def task(_progress):
            total = len(open_reader(input_path, purpose=READ).pages)
            items = []
            for level, title, page_text in rows:
                page = page_text.strip()
                if page and not (page.isdigit() and 1 <= int(page) <= total):
                    raise ValueError(
                        tr('A página "{page}" do marcador "{title}" não existe: o documento tem {total} página(s).').format(
                            page=page, title=title, total=total
                        )
                    )
                items.append(OutlineItem(level, title.strip(), int(page) - 1 if page else None))
            SetOutline().run(input_path, output_path, items)

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(self, tr("Marcadores"), tr("Marcadores salvos com sucesso."))

        run_task(
            self,
            tr("Marcadores"),
            task,
            on_success=done,
            error_message=tr("Falha ao salvar marcadores: {error}"),
        )
