"""Aba de edição: substituir imagens embutidas, "editar" texto (cobrir e reescrever) e
gerenciar links (hyperlinks)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.edit_text import EditTextArea, TextEditRect
from core.extract_images import ListEmbeddedImages, ReplaceEmbeddedImage
from core.links import AddLink, LinkInfo, ListLinks, RemoveLink
from ui.area_pick_state import AreaPickState
from ui.i18n import plural, tr, tr_message
from ui.tasks import call, call_with_progress, run_task
from ui.widgets.color_combo import ColorCombo
from ui.widgets.current_page import with_current_page_button
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_info, notify_success

_MODES = ["Substituir imagem", "Editar texto", "Adicionar link", "Listar links", "Remover link"]
_EDIT_TEXT_MODE = 1
_ADD_LINK_MODE = 2
_REMOVE_LINK_MODE = 4
# Modos em que o arrasto no visualizador marca uma área (ou escolhe o link a remover).
_PICK_MODES = (_EDIT_TEXT_MODE, _ADD_LINK_MODE, _REMOVE_LINK_MODE)
_EDIT_FONTS = [("sans", "Sem serifa"), ("sans-bold", "Sem serifa, negrito"), ("mono", "Monoespaçada")]
_TEXT_COLUMN = 5


class EditPage(QWidget):
    """Permite substituir imagens embutidas, cobrir e reescrever texto, e adicionar,
    listar ou remover links (hyperlinks) de um PDF."""

    def __init__(self, session, area_pick_state: AreaPickState | None = None, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.area_pick_state = area_pick_state or AreaPickState()
        self.area_pick_state.area_picked.connect(self._on_area_picked)

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr(mode) for mode in _MODES])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_replace_image_panel())
        self.stack.addWidget(self._build_edit_text_panel())
        self.stack.addWidget(self._build_add_link_panel())
        self.stack.addWidget(self._build_list_links_panel())
        self.stack.addWidget(self._build_remove_link_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        self.area_pick_state.set_wanted(self, index in _PICK_MODES)
        self._publish_areas()

    def _on_area_picked(self, page_index: int, left: float, bottom: float, right: float, top: float):
        if self.area_pick_state.owner() is not self:
            return
        mode = self.mode_combo.currentIndex()
        if mode == _EDIT_TEXT_MODE:
            self._add_edit_text_row(page_index + 1, (left, bottom, right, top))
            self.edit_text_editor.setFocus()
        elif mode == _REMOVE_LINK_MODE:
            self._select_link_at(page_index, ((left + right) / 2, (bottom + top) / 2))
        elif mode == _ADD_LINK_MODE:
            self.link_page_spin.setValue(page_index + 1)
            for spin, value in zip(
                (self.link_left_spin, self.link_bottom_spin, self.link_right_spin, self.link_top_spin),
                (left, bottom, right, top),
            ):
                spin.setValue(value)
            self._publish_areas()

    # ---- Substituir imagem --------------------------------------------------

    def _build_replace_image_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        list_button = QPushButton(tr("Listar imagens"))
        list_button.clicked.connect(self._list_images)
        self.images_list = QListWidget()
        self.images_list.setToolTip(tr("Clique numa imagem para escolhê-la."))
        self.images_list.currentItemChanged.connect(self._on_image_chosen)

        self.image_page_spin = QSpinBox()
        self.image_page_spin.setRange(1, 9999)
        self.image_index_spin = QSpinBox()
        self.image_index_spin.setRange(1, 9999)

        self.new_image_picker = FilePicker(
            mode="open", file_filter="Imagens (*.png *.jpg *.jpeg *.bmp *.tiff)"
        )
        self.image_fit_combo = QComboBox()
        self.image_fit_combo.addItem(tr("Ajustar sem distorcer (sobra transparente)"), "contain")
        self.image_fit_combo.addItem(tr("Esticar para ocupar a área toda"), "stretch")
        self.replace_image_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="imagem_substituida"
        )
        replace_button = QPushButton(tr("Substituir imagem"))
        self.action_buttons.append(replace_button)
        replace_button.clicked.connect(self._replace_image)

        layout.addWidget(list_button)
        layout.addWidget(self.images_list)
        layout.addWidget(QLabel(tr("Página:")))
        layout.addWidget(self.image_page_spin)
        layout.addWidget(QLabel(tr("Número da imagem na página:")))
        layout.addWidget(self.image_index_spin)
        layout.addWidget(QLabel(tr("Nova imagem:")))
        layout.addWidget(self.new_image_picker)
        layout.addWidget(QLabel(tr("Se a proporção for diferente:")))
        layout.addWidget(self.image_fit_combo)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.replace_image_output_picker)
        layout.addWidget(replace_button)
        return widget

    def _list_images(self):
        input_path = self.session.path()
        self.images_list.clear()
        if not input_path:
            notify_error(self, tr("Substituir imagem"), tr("Abra um PDF para começar."))
            return

        task = call(ListEmbeddedImages().run, input_path)

        def done(images):
            if not images:
                self.images_list.addItem(tr("Nenhuma imagem embutida encontrada."))
                return
            for image in images:
                item = QListWidgetItem(
                    f"{tr('Página')} {image.page_index + 1} — #{image.image_index + 1} — "
                    f"{image.name} ({image.width}x{image.height})"
                )
                item.setData(Qt.ItemDataRole.UserRole, (image.page_index, image.image_index))
                self.images_list.addItem(item)

        run_task(
            self,
            tr("Substituir imagem"),
            task,
            on_success=done,
            error_message=tr("Falha ao listar imagens: {error}"),
        )

    def _on_image_chosen(self, item, _previous=None):
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if data:
            page_index, image_index = data
            self.image_page_spin.setValue(page_index + 1)
            self.image_index_spin.setValue(image_index + 1)

    def _replace_image(self):
        input_path = self.session.path()
        new_image_path = self.new_image_picker.path()
        output_path = self.replace_image_output_picker.path()

        if not input_path:
            notify_error(self, tr("Substituir imagem"), tr("Abra um PDF para começar."))
            return
        if not new_image_path:
            notify_error(self, tr("Substituir imagem"), tr("Escolha a nova imagem."))
            return
        if not output_path:
            notify_error(self, tr("Substituir imagem"), tr("Escolha o arquivo de saída."))
            return

        task = call(
            ReplaceEmbeddedImage().run,
            input_path,
            output_path,
            page_number=self.image_page_spin.value() - 1,
            image_index=self.image_index_spin.value() - 1,
            new_image_path=new_image_path,
            fit=self.image_fit_combo.currentData(),
        )

        def done(result):
            self.session.open(output_path)
            message = tr("Imagem substituída com sucesso.")
            if result.other_pages:
                pages = ", ".join(str(index + 1) for index in result.other_pages)
                message += "\n\n" + plural(
                    len(result.other_pages),
                    "A mesma imagem também aparecia na página {pages}, que mudou junto.",
                    "A mesma imagem também aparecia nas páginas {pages}, que mudaram junto.",
                    pages=pages,
                )
            notify_success(self, tr("Substituir imagem"), message)

        run_task(
            self,
            tr("Substituir imagem"),
            task,
            on_success=done,
            error_message=tr("Falha ao substituir imagem: {error}"),
        )

    # ---- Editar texto (cobrir e reescrever) ----------------------------------

    def _build_edit_text_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Cobre a área marcada e desenha o texto novo por cima, achatando a página em "
                "imagem (como na redação) — não é edição do texto original, e a página "
                "inteira perde a camada de texto pesquisável."
            )
        )
        note.setWordWrap(True)
        hint = QLabel(tr("Arraste no visualizador para marcar cada área. As coordenadas (em pontos PDF) podem ser ajustadas na tabela."))
        hint.setWordWrap(True)

        self.edit_text_table = QTableWidget(0, 6)
        self.edit_text_table.setHorizontalHeaderLabels(
            [tr("Página"), tr("Esquerda"), tr("Base"), tr("Direita"), tr("Topo"), tr("Texto novo")]
        )
        header = self.edit_text_table.horizontalHeader()
        for column in range(_TEXT_COLUMN):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_TEXT_COLUMN, QHeaderView.ResizeMode.Stretch)
        self.edit_text_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.edit_text_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.edit_text_table.itemChanged.connect(self._on_edit_table_changed)
        self.edit_text_table.currentCellChanged.connect(self._on_edit_row_selected)

        add_row_button = QPushButton(tr("Adicionar área"))
        add_row_button.clicked.connect(lambda: self._add_edit_text_row())
        remove_row_button = QPushButton(tr("Remover área"))
        remove_row_button.clicked.connect(self._remove_edit_text_row)
        row_buttons_layout = QHBoxLayout()
        row_buttons_layout.addWidget(add_row_button)
        row_buttons_layout.addWidget(remove_row_button)

        self.edit_text_editor = QPlainTextEdit()
        self.edit_text_editor.setPlaceholderText(tr("Texto novo da área selecionada (Enter quebra a linha)"))
        self.edit_text_editor.setMaximumHeight(90)
        self.edit_text_editor.textChanged.connect(self._on_edit_text_typed)

        self.edit_text_font_combo = QComboBox()
        for key, label in _EDIT_FONTS:
            self.edit_text_font_combo.addItem(tr(label), key)
        self.edit_text_font_size_spin = QDoubleSpinBox()
        self.edit_text_font_size_spin.setRange(4, 96)
        self.edit_text_font_size_spin.setValue(12)
        self.edit_text_color_combo = ColorCombo("000000")
        self.edit_text_cover_combo = ColorCombo("ffffff")

        options = QFormLayout()
        options.addRow(tr("Fonte:"), self.edit_text_font_combo)
        options.addRow(tr("Tamanho do texto novo:"), self.edit_text_font_size_spin)
        options.addRow(tr("Cor do texto:"), self.edit_text_color_combo)
        options.addRow(tr("Cor de fundo da área:"), self.edit_text_cover_combo)

        self.edit_text_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="texto_editado"
        )
        apply_button = QPushButton(tr("Aplicar edição"))
        self.action_buttons.append(apply_button)
        apply_button.clicked.connect(self._apply_edit_text)

        layout.addWidget(note)
        layout.addWidget(hint)
        layout.addWidget(self.edit_text_table)
        layout.addLayout(row_buttons_layout)
        layout.addWidget(self.edit_text_editor)
        layout.addLayout(options)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.edit_text_output_picker)
        layout.addWidget(apply_button)
        return widget

    def _add_edit_text_row(self, page_number: int | None = None, rect=None) -> int:
        if page_number is None:
            page_number = 1
        left, bottom, right, top = rect or (72, 700, 272, 730)
        row = self.edit_text_table.rowCount()
        self.edit_text_table.blockSignals(True)
        self.edit_text_table.insertRow(row)
        for column, value in enumerate([str(page_number), f"{left:.1f}", f"{bottom:.1f}", f"{right:.1f}", f"{top:.1f}", ""]):
            self.edit_text_table.setItem(row, column, QTableWidgetItem(value))
        self.edit_text_table.blockSignals(False)
        self.edit_text_table.setCurrentCell(row, _TEXT_COLUMN)
        self._publish_areas()
        return row

    def _remove_edit_text_row(self):
        row = self.edit_text_table.currentRow()
        if row >= 0:
            self.edit_text_table.removeRow(row)
            self._publish_areas()

    def _on_edit_row_selected(self, row: int, _column: int, _previous_row: int, _previous_column: int):
        item = self.edit_text_table.item(row, _TEXT_COLUMN) if row >= 0 else None
        self.edit_text_editor.blockSignals(True)
        self.edit_text_editor.setPlainText(item.text() if item is not None else "")
        self.edit_text_editor.setEnabled(item is not None)
        self.edit_text_editor.blockSignals(False)
        self._publish_areas()

    def _on_edit_text_typed(self):
        row = self.edit_text_table.currentRow()
        item = self.edit_text_table.item(row, _TEXT_COLUMN) if row >= 0 else None
        if item is not None:
            self.edit_text_table.blockSignals(True)
            item.setText(self.edit_text_editor.toPlainText())
            self.edit_text_table.blockSignals(False)

    def _on_edit_table_changed(self, item: QTableWidgetItem):
        if item.column() == _TEXT_COLUMN and item.row() == self.edit_text_table.currentRow():
            self.edit_text_editor.blockSignals(True)
            self.edit_text_editor.setPlainText(item.text())
            self.edit_text_editor.blockSignals(False)
        self._publish_areas()

    def _table_areas(self) -> list:
        """(página a partir de 0, (left, bottom, right, top)) de cada linha que dá para ler."""
        areas = []
        for row in range(self.edit_text_table.rowCount()):
            try:
                values = [float((self.edit_text_table.item(row, column) or QTableWidgetItem()).text()) for column in range(5)]
            except ValueError:
                areas.append((-1, (0.0, 0.0, 0.0, 0.0)))  # linha inválida: mantém a numeração
                continue
            page, left, bottom, right, top = values
            areas.append((int(page) - 1, (left, bottom, right, top)))
        return areas

    def _publish_areas(self):
        if not hasattr(self, "remove_links_list"):
            return  # ainda construindo os painéis
        if self.mode_combo.currentIndex() == _REMOVE_LINK_MODE:
            links = self._loaded_links
            selected = self.remove_links_list.currentRow()
            self.area_pick_state.set_areas(
                self, [(link.page_index, link.rect) for link in links], selected if selected >= 0 else None
            )
            return
        if self.mode_combo.currentIndex() == _ADD_LINK_MODE:
            rect = tuple(
                spin.value()
                for spin in (self.link_left_spin, self.link_bottom_spin, self.link_right_spin, self.link_top_spin)
            )
            self.area_pick_state.set_areas(self, [(self.link_page_spin.value() - 1, rect)], 0)
            return
        row = self.edit_text_table.currentRow()
        self.area_pick_state.set_areas(self, self._table_areas(), row if row >= 0 else None)

    def _apply_edit_text(self):
        input_path = self.session.path()
        output_path = self.edit_text_output_picker.path()

        if not input_path:
            notify_error(self, tr("Editar texto"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Editar texto"), tr("Escolha o arquivo de saída."))
            return

        try:
            edits = []
            area_rows = []
            for row in range(self.edit_text_table.rowCount()):
                new_text = self.edit_text_table.item(row, _TEXT_COLUMN).text()
                if not new_text.strip():
                    continue
                page_index = int(self.edit_text_table.item(row, 0).text()) - 1
                left, bottom, right, top = (float(self.edit_text_table.item(row, c).text()) for c in range(1, 5))
                edits.append(
                    TextEditRect(
                        page_index=page_index,
                        left=min(left, right),
                        bottom=min(bottom, top),
                        right=max(left, right),
                        top=max(bottom, top),
                        new_text=new_text,
                        font_size=self.edit_text_font_size_spin.value(),
                        text_color=self.edit_text_color_combo.color(),
                        cover_color=self.edit_text_cover_combo.color(),
                        font=self.edit_text_font_combo.currentData(),
                    )
                )
                area_rows.append(row + 1)
        except ValueError:
            notify_error(
                self,
                tr("Editar texto"),
                tr("Página e as coordenadas precisam ser números em todas as linhas preenchidas."),
            )
            return

        if not edits:
            notify_error(self, tr("Editar texto"), tr("Marque pelo menos uma área com texto novo."))
            return

        task = call_with_progress(EditTextArea().run, input_path, output_path, edits)

        def done(result):
            self.session.open(output_path)
            message = plural(result.pages_edited, "1 página editada.", "{count} páginas editadas.")
            if result.clipped:
                areas = ", ".join(str(area_rows[index]) for index in result.clipped)
                message += "\n\n" + plural(
                    len(result.clipped),
                    "O texto não coube inteiro na área {areas}: o que não coube ficou de fora. "
                    "Aumente a área ou diminua a fonte.",
                    "O texto não coube inteiro nas áreas {areas}: o que não coube ficou de fora. "
                    "Aumente as áreas ou diminua a fonte.",
                    areas=areas,
                )
            notify_success(self, tr("Editar texto"), message)

        run_task(
            self,
            tr("Editar texto"),
            task,
            on_success=done,
            error_message=tr("Falha ao editar texto: {error}"),
        )

    # ---- Adicionar link -------------------------------------------------------

    def _build_add_link_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(tr("Arraste no visualizador para marcar a área do link, ou ajuste os valores abaixo."))
        hint.setWordWrap(True)
        self.link_page_spin = QSpinBox()
        self.link_page_spin.setRange(1, 9999)

        self.link_left_spin = QDoubleSpinBox()
        self.link_left_spin.setRange(0, 20000)
        self.link_bottom_spin = QDoubleSpinBox()
        self.link_bottom_spin.setRange(0, 20000)
        self.link_right_spin = QDoubleSpinBox()
        self.link_right_spin.setRange(0, 20000)
        self.link_right_spin.setValue(100)
        self.link_top_spin = QDoubleSpinBox()
        self.link_top_spin.setRange(0, 20000)
        self.link_top_spin.setValue(20)

        self.link_target_combo = QComboBox()
        self.link_target_combo.addItems([tr("URL externa"), tr("Página do documento")])
        self.link_target_combo.currentIndexChanged.connect(self._on_link_target_changed)

        self.link_target_stack = QStackedWidget()
        self.link_url_edit = QLineEdit()
        self.link_url_edit.setPlaceholderText(tr("https://exemplo.com"))
        self.link_target_page_spin = QSpinBox()
        self.link_target_page_spin.setRange(1, 9999)
        self.link_target_stack.addWidget(self.link_url_edit)
        target_page_widget = QWidget()
        target_page_layout = with_current_page_button(self.link_target_page_spin, self.session)
        target_page_layout.setContentsMargins(0, 0, 0, 0)
        target_page_widget.setLayout(target_page_layout)
        self.link_target_stack.addWidget(target_page_widget)

        self.add_link_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="com_link"
        )
        add_button = QPushButton(tr("Adicionar link"))
        self.action_buttons.append(add_button)
        add_button.clicked.connect(self._add_link)

        layout.addWidget(hint)
        layout.addWidget(QLabel(tr("Página:")))
        layout.addWidget(self.link_page_spin)
        layout.addWidget(QLabel(tr("Esquerda / Base / Direita / Topo (pontos PDF):")))
        for spin in (self.link_page_spin, self.link_left_spin, self.link_bottom_spin, self.link_right_spin, self.link_top_spin):
            spin.valueChanged.connect(self._publish_areas)
        for spin in (self.link_left_spin, self.link_bottom_spin, self.link_right_spin, self.link_top_spin):
            layout.addWidget(spin)
        layout.addWidget(QLabel(tr("Destino:")))
        layout.addWidget(self.link_target_combo)
        layout.addWidget(self.link_target_stack)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.add_link_output_picker)
        layout.addWidget(add_button)
        return widget

    def _on_link_target_changed(self, index: int):
        self.link_target_stack.setCurrentIndex(index)

    def _add_link(self):
        input_path = self.session.path()
        output_path = self.add_link_output_picker.path()

        if not input_path:
            notify_error(self, tr("Adicionar link"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Adicionar link"), tr("Escolha o arquivo de saída."))
            return

        is_url = self.link_target_combo.currentIndex() == 0
        url = self.link_url_edit.text().strip() or None if is_url else None
        target_page = None if is_url else self.link_target_page_spin.value() - 1
        if is_url and not url:
            notify_error(self, tr("Adicionar link"), tr("Digite a URL de destino."))
            return

        task = call(
            AddLink().run,
            input_path,
            output_path,
            page_number=self.link_page_spin.value() - 1,
            left=self.link_left_spin.value(),
            bottom=self.link_bottom_spin.value(),
            right=self.link_right_spin.value(),
            top=self.link_top_spin.value(),
            url=url,
            target_page=target_page,
        )

        def done(_result):
            self.session.open(output_path)
            notify_success(self, tr("Adicionar link"), tr("Link adicionado com sucesso."))

        run_task(
            self,
            tr("Adicionar link"),
            task,
            on_success=done,
            error_message=tr("Falha ao adicionar link: {error}"),
        )

    # ---- Listar links -----------------------------------------------------------

    def _build_list_links_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        list_button = QPushButton(tr("Listar links"))
        self.action_buttons.append(list_button)
        list_button.clicked.connect(self._list_links)
        self.links_list = QListWidget()

        layout.addWidget(list_button)
        layout.addWidget(self.links_list)
        return widget

    def _list_links(self):
        input_path = self.session.path()
        self.links_list.clear()
        if not input_path:
            notify_error(self, tr("Listar links"), tr("Abra um PDF para começar."))
            return

        task = call(ListLinks().run, input_path)

        def done(links):
            if not links:
                self.links_list.addItem(tr("Nenhum link encontrado."))
                return
            for link in links:
                self.links_list.addItem(
                    f"{tr('Página')} {link.page_index + 1} — #{link.link_index + 1} — {tr_message(link.target)}"
                )

        run_task(
            self,
            tr("Listar links"),
            task,
            on_success=done,
            error_message=tr("Falha ao listar links: {error}"),
        )

    # ---- Remover link -------------------------------------------------------------

    def _build_remove_link_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(tr("Clique num link da lista, ou arraste sobre ele no visualizador, para escolher o link a remover."))
        note.setWordWrap(True)
        load_button = QPushButton(tr("Listar links"))
        load_button.clicked.connect(self._load_links_to_remove)
        self.remove_links_list = QListWidget()
        self.remove_links_list.currentRowChanged.connect(self._on_link_to_remove_chosen)
        self._loaded_links: list[LinkInfo] = []

        self.remove_link_page_spin = QSpinBox()
        self.remove_link_page_spin.setRange(1, 9999)
        self.remove_link_index_spin = QSpinBox()
        self.remove_link_index_spin.setRange(1, 9999)

        self.remove_link_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="sem_link"
        )
        remove_button = QPushButton(tr("Remover link"))
        self.action_buttons.append(remove_button)
        remove_button.clicked.connect(self._remove_link)

        layout.addWidget(note)
        layout.addWidget(load_button)
        layout.addWidget(self.remove_links_list)
        layout.addWidget(QLabel(tr("Página:")))
        layout.addWidget(self.remove_link_page_spin)
        layout.addWidget(QLabel(tr("Número do link na página:")))
        layout.addWidget(self.remove_link_index_spin)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.remove_link_output_picker)
        layout.addWidget(remove_button)
        return widget

    def _load_links_to_remove(self):
        input_path = self.session.path()
        if not input_path:
            notify_error(self, tr("Remover link"), tr("Abra um PDF para começar."))
            return

        def done(links):
            self._loaded_links = list(links)
            self.remove_links_list.blockSignals(True)
            self.remove_links_list.clear()
            for link in links:
                self.remove_links_list.addItem(
                    f"{tr('Página')} {link.page_index + 1} — #{link.link_index + 1} — {tr_message(link.target)}"
                )
            self.remove_links_list.blockSignals(False)
            if not links:
                notify_info(self, tr("Remover link"), tr("Nenhum link encontrado."))
            self._publish_areas()

        run_task(
            self,
            tr("Listar links"),
            call(ListLinks().run, input_path),
            on_success=done,
            error_message=tr("Falha ao listar links: {error}"),
        )

    def _on_link_to_remove_chosen(self, row: int):
        if 0 <= row < len(self._loaded_links):
            link = self._loaded_links[row]
            self.remove_link_page_spin.setValue(link.page_index + 1)
            self.remove_link_index_spin.setValue(link.link_index + 1)
        self._publish_areas()

    def _select_link_at(self, page_index: int, point: tuple[float, float]) -> None:
        x, y = point
        for row, link in enumerate(self._loaded_links):
            left, bottom, right, top = link.rect
            if link.page_index == page_index and min(left, right) <= x <= max(left, right) and min(bottom, top) <= y <= max(bottom, top):
                self.remove_links_list.setCurrentRow(row)
                return

    def _remove_link(self):
        input_path = self.session.path()
        output_path = self.remove_link_output_picker.path()

        if not input_path:
            notify_error(self, tr("Remover link"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Remover link"), tr("Escolha o arquivo de saída."))
            return

        task = call(
            RemoveLink().run,
            input_path,
            output_path,
            page_number=self.remove_link_page_spin.value() - 1,
            link_index=self.remove_link_index_spin.value() - 1,
        )

        def done(_result):
            self.session.open(output_path)
            self._loaded_links = []
            self.remove_links_list.clear()
            self._publish_areas()
            notify_success(self, tr("Remover link"), tr("Link removido com sucesso."))

        run_task(
            self,
            tr("Remover link"),
            task,
            on_success=done,
            error_message=tr("Falha ao remover link: {error}"),
        )
