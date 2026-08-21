"""Aba de edição: substituir imagens embutidas, "editar" texto (cobrir e reescrever) e
gerenciar links (hyperlinks)."""

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
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
from core.links import AddLink, ListLinks, RemoveLink
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_MODES = ["Substituir imagem", "Editar texto", "Adicionar link", "Listar links", "Remover link"]


class EditPage(QWidget):
    """Permite substituir imagens embutidas, cobrir e reescrever texto, e adicionar,
    listar ou remover links (hyperlinks) de um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

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

    # ---- Substituir imagem --------------------------------------------------

    def _build_replace_image_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        list_button = QPushButton(tr("Listar imagens"))
        list_button.clicked.connect(self._list_images)
        self.images_list = QListWidget()

        self.image_page_spin = QSpinBox()
        self.image_page_spin.setRange(0, 9999)
        self.image_index_spin = QSpinBox()
        self.image_index_spin.setRange(0, 9999)

        self.new_image_picker = FilePicker(
            mode="open", file_filter="Imagens (*.png *.jpg *.jpeg *.bmp *.tiff)"
        )
        self.replace_image_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="imagem_substituida"
        )
        replace_button = QPushButton(tr("Substituir imagem"))
        replace_button.clicked.connect(self._replace_image)

        layout.addWidget(list_button)
        layout.addWidget(self.images_list)
        layout.addWidget(QLabel(tr("Página (0 = primeira):")))
        layout.addWidget(self.image_page_spin)
        layout.addWidget(QLabel(tr("Índice da imagem na página:")))
        layout.addWidget(self.image_index_spin)
        layout.addWidget(QLabel(tr("Nova imagem:")))
        layout.addWidget(self.new_image_picker)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.replace_image_output_picker)
        layout.addWidget(replace_button)
        return widget

    def _list_images(self):
        input_path = self.session.path()
        self.images_list.clear()
        if not input_path:
            QMessageBox.warning(self, tr("Substituir imagem"), tr("Abra um PDF para começar."))
            return

        try:
            images = ListEmbeddedImages().run(input_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Substituir imagem"), tr("Falha ao listar imagens: {error}").format(error=exc)
            )
            return

        if not images:
            self.images_list.addItem(tr("Nenhuma imagem embutida encontrada."))
            return
        for image in images:
            self.images_list.addItem(
                f"{tr('Página')} {image.page_index} — #{image.image_index} — "
                f"{image.name} ({image.width}x{image.height})"
            )

    def _replace_image(self):
        input_path = self.session.path()
        new_image_path = self.new_image_picker.path()
        output_path = self.replace_image_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Substituir imagem"), tr("Abra um PDF para começar."))
            return
        if not new_image_path:
            QMessageBox.warning(self, tr("Substituir imagem"), tr("Escolha a nova imagem."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Substituir imagem"), tr("Escolha o arquivo de saída."))
            return

        try:
            ReplaceEmbeddedImage().run(
                input_path,
                output_path,
                page_number=self.image_page_spin.value(),
                image_index=self.image_index_spin.value(),
                new_image_path=new_image_path,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("Substituir imagem"),
                tr("Falha ao substituir imagem: {error}").format(error=exc),
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Substituir imagem"), tr("Imagem substituída com sucesso."))

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

        self.edit_text_table = QTableWidget(0, 6)
        self.edit_text_table.setHorizontalHeaderLabels(
            [tr("Página"), "Left", "Bottom", "Right", "Top", tr("Texto novo")]
        )

        add_row_button = QPushButton(tr("Adicionar área"))
        add_row_button.clicked.connect(self._add_edit_text_row)
        remove_row_button = QPushButton(tr("Remover área"))
        remove_row_button.clicked.connect(self._remove_edit_text_row)
        row_buttons_layout = QHBoxLayout()
        row_buttons_layout.addWidget(add_row_button)
        row_buttons_layout.addWidget(remove_row_button)

        self.edit_text_font_size_spin = QDoubleSpinBox()
        self.edit_text_font_size_spin.setRange(4, 96)
        self.edit_text_font_size_spin.setValue(12)

        self.edit_text_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="texto_editado"
        )
        apply_button = QPushButton(tr("Aplicar edição"))
        apply_button.clicked.connect(self._apply_edit_text)

        layout.addWidget(note)
        layout.addWidget(self.edit_text_table)
        layout.addLayout(row_buttons_layout)
        layout.addWidget(QLabel(tr("Tamanho do texto novo:")))
        layout.addWidget(self.edit_text_font_size_spin)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.edit_text_output_picker)
        layout.addWidget(apply_button)
        self._add_edit_text_row()
        return widget

    def _add_edit_text_row(self):
        row = self.edit_text_table.rowCount()
        self.edit_text_table.insertRow(row)
        for column, default in enumerate(["0", "0", "0", "100", "20", ""]):
            self.edit_text_table.setItem(row, column, QTableWidgetItem(default))

    def _remove_edit_text_row(self):
        row = self.edit_text_table.currentRow()
        if row >= 0:
            self.edit_text_table.removeRow(row)

    def _apply_edit_text(self):
        input_path = self.session.path()
        output_path = self.edit_text_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Editar texto"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Editar texto"), tr("Escolha o arquivo de saída."))
            return

        try:
            edits = []
            for row in range(self.edit_text_table.rowCount()):
                new_text = self.edit_text_table.item(row, 5).text()
                if not new_text:
                    continue
                page_index = int(self.edit_text_table.item(row, 0).text())
                left = float(self.edit_text_table.item(row, 1).text())
                bottom = float(self.edit_text_table.item(row, 2).text())
                right = float(self.edit_text_table.item(row, 3).text())
                top = float(self.edit_text_table.item(row, 4).text())
                edits.append(
                    TextEditRect(
                        page_index=page_index,
                        left=left,
                        bottom=bottom,
                        right=right,
                        top=top,
                        new_text=new_text,
                        font_size=self.edit_text_font_size_spin.value(),
                    )
                )
        except ValueError:
            QMessageBox.warning(
                self,
                tr("Editar texto"),
                tr("Página e as coordenadas precisam ser números em todas as linhas preenchidas."),
            )
            return

        if not edits:
            QMessageBox.warning(self, tr("Editar texto"), tr("Marque pelo menos uma área com texto novo."))
            return

        try:
            pages_edited = EditTextArea().run(input_path, output_path, edits)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Editar texto"), tr("Falha ao editar texto: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(
            self,
            tr("Editar texto"),
            tr("{count} página(s) editada(s) com sucesso.").format(count=pages_edited),
        )

    # ---- Adicionar link -------------------------------------------------------

    def _build_add_link_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.link_page_spin = QSpinBox()
        self.link_page_spin.setRange(0, 9999)

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
        self.link_target_page_spin.setRange(0, 9999)
        self.link_target_stack.addWidget(self.link_url_edit)
        self.link_target_stack.addWidget(self.link_target_page_spin)

        self.add_link_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="com_link"
        )
        add_button = QPushButton(tr("Adicionar link"))
        add_button.clicked.connect(self._add_link)

        layout.addWidget(QLabel(tr("Página (0 = primeira):")))
        layout.addWidget(self.link_page_spin)
        layout.addWidget(QLabel("Left / Bottom / Right / Top:"))
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
            QMessageBox.warning(self, tr("Adicionar link"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Adicionar link"), tr("Escolha o arquivo de saída."))
            return

        is_url = self.link_target_combo.currentIndex() == 0
        url = self.link_url_edit.text().strip() or None if is_url else None
        target_page = None if is_url else self.link_target_page_spin.value()
        if is_url and not url:
            QMessageBox.warning(self, tr("Adicionar link"), tr("Digite a URL de destino."))
            return

        try:
            AddLink().run(
                input_path,
                output_path,
                page_number=self.link_page_spin.value(),
                left=self.link_left_spin.value(),
                bottom=self.link_bottom_spin.value(),
                right=self.link_right_spin.value(),
                top=self.link_top_spin.value(),
                url=url,
                target_page=target_page,
            )
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Adicionar link"), tr("Falha ao adicionar link: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Adicionar link"), tr("Link adicionado com sucesso."))

    # ---- Listar links -----------------------------------------------------------

    def _build_list_links_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        list_button = QPushButton(tr("Listar links"))
        list_button.clicked.connect(self._list_links)
        self.links_list = QListWidget()

        layout.addWidget(list_button)
        layout.addWidget(self.links_list)
        return widget

    def _list_links(self):
        input_path = self.session.path()
        self.links_list.clear()
        if not input_path:
            QMessageBox.warning(self, tr("Listar links"), tr("Abra um PDF para começar."))
            return

        try:
            links = ListLinks().run(input_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Listar links"), tr("Falha ao listar links: {error}").format(error=exc)
            )
            return

        if not links:
            self.links_list.addItem(tr("Nenhum link encontrado."))
            return
        for link in links:
            self.links_list.addItem(
                f"{tr('Página')} {link.page_index} — #{link.link_index} — {link.target}"
            )

    # ---- Remover link -------------------------------------------------------------

    def _build_remove_link_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(tr('Use "Listar links" para descobrir a página e o índice do link a remover.'))
        note.setWordWrap(True)

        self.remove_link_page_spin = QSpinBox()
        self.remove_link_page_spin.setRange(0, 9999)
        self.remove_link_index_spin = QSpinBox()
        self.remove_link_index_spin.setRange(0, 9999)

        self.remove_link_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="sem_link"
        )
        remove_button = QPushButton(tr("Remover link"))
        remove_button.clicked.connect(self._remove_link)

        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Página (0 = primeira):")))
        layout.addWidget(self.remove_link_page_spin)
        layout.addWidget(QLabel(tr("Índice do link na página:")))
        layout.addWidget(self.remove_link_index_spin)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.remove_link_output_picker)
        layout.addWidget(remove_button)
        return widget

    def _remove_link(self):
        input_path = self.session.path()
        output_path = self.remove_link_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Remover link"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Remover link"), tr("Escolha o arquivo de saída."))
            return

        try:
            RemoveLink().run(
                input_path,
                output_path,
                page_number=self.remove_link_page_spin.value(),
                link_index=self.remove_link_index_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Remover link"), tr("Falha ao remover link: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Remover link"), tr("Link removido com sucesso."))
