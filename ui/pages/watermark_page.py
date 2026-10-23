"""Aba de marca d'água em PDFs."""

import pypdfium2 as pdfium
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base import READ, open_reader
from core.progress import PDFIUM_LOCK
from core.watermark import AddWatermark, watermark_preview
from ui.i18n import tr
from ui.page_ranges import format_page_ranges, parse_page_ranges
from ui.tasks import call, run_task
from ui.viewer.render import render_page
from ui.widgets.color_combo import ColorCombo
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_POSITIONS = (
    ("Centro", "center"),
    ("Canto superior esquerdo", "top-left"),
    ("Canto superior direito", "top-right"),
    ("Canto inferior esquerdo", "bottom-left"),
    ("Canto inferior direito", "bottom-right"),
    ("Mosaico (repetida pela página)", "tile"),
)
_PREVIEW_SIZE = 320  # pixels do lado maior da pré-visualização


class WatermarkPage(QWidget):
    """Permite adicionar uma marca d'água de texto ou imagem às páginas de um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="marca_dagua"
        )

        self.kind_combo = QComboBox()
        self.kind_combo.addItems([tr("Texto"), tr("Imagem ou logotipo")])

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText(tr("Texto da marca d'água, ex: CONFIDENCIAL"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 200)
        self.font_size_spin.setValue(40)
        self.color_combo = ColorCombo("000000")
        text_panel = QWidget()
        text_form = QFormLayout(text_panel)
        text_form.setContentsMargins(0, 0, 0, 0)
        text_form.addRow(tr("Texto:"), self.text_edit)
        text_form.addRow(tr("Tamanho da fonte:"), self.font_size_spin)
        text_form.addRow(tr("Cor:"), self.color_combo)

        self.image_picker = FilePicker(mode="open", file_filter=tr("Imagens") + " (*.png *.jpg *.jpeg *.bmp *.tiff *.webp)")
        self.image_width_spin = QSpinBox()
        self.image_width_spin.setRange(5, 100)
        self.image_width_spin.setValue(30)
        self.image_width_spin.setSuffix(" %")
        self.image_width_spin.setToolTip(tr("Largura da imagem em relação à largura da página."))
        image_panel = QWidget()
        image_form = QFormLayout(image_panel)
        image_form.setContentsMargins(0, 0, 0, 0)
        image_form.addRow(tr("Imagem:"), self.image_picker)
        image_form.addRow(tr("Largura:"), self.image_width_spin)

        self.kind_stack = QStackedWidget()
        self.kind_stack.addWidget(text_panel)
        self.kind_stack.addWidget(image_panel)
        self.kind_combo.currentIndexChanged.connect(self.kind_stack.setCurrentIndex)

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.05, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setValue(0.3)

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 359)
        self.rotation_spin.setValue(45)

        self.position_combo = QComboBox()
        for label, value in _POSITIONS:
            self.position_combo.addItem(tr(label), value)

        self.behind_check = QCheckBox(tr("Atrás do conteúdo"))
        self.behind_check.setToolTip(
            tr("Como um papel timbrado: o texto da página fica por cima. Some em páginas escaneadas, que cobrem a página inteira.")
        )

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText(tr("Páginas (vazio = todas), ex: 1, 3-5"))
        self.selection_button = QPushButton(tr("Usar seleção"))
        self.selection_button.setToolTip(tr("Preenche com as páginas selecionadas nas miniaturas (Ctrl ou Shift + clique)."))
        self.selection_button.clicked.connect(lambda: self.pages_edit.setText(format_page_ranges(session.selected_pages())))
        pages_row = QHBoxLayout()
        pages_row.addWidget(self.pages_edit, 1)
        pages_row.addWidget(self.selection_button)

        options_layout = QFormLayout()
        options_layout.addRow(tr("Opacidade:"), self.opacity_spin)
        options_layout.addRow(tr("Rotação:"), self.rotation_spin)
        options_layout.addRow(tr("Posição:"), self.position_combo)
        options_layout.addRow("", self.behind_check)
        options_layout.addRow(tr("Páginas:"), pages_row)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_button = QPushButton(tr("Pré-visualizar"))
        preview_button.setToolTip(tr("Mostra a página atual do visualizador com a marca d'água, sem gravar nada."))
        preview_button.clicked.connect(self._preview)
        apply_button = QPushButton(tr("Aplicar marca d'água"))
        apply_button.clicked.connect(self._apply)
        buttons = QHBoxLayout()
        buttons.addWidget(preview_button)
        buttons.addWidget(apply_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Marca d'água:")))
        layout.addWidget(self.kind_combo)
        layout.addWidget(self.kind_stack)
        layout.addLayout(options_layout)
        layout.addLayout(buttons)
        layout.addWidget(self.preview_label)

    def _options(self) -> dict | None:
        """As opções de `AddWatermark.run`, ou None (com o aviso) se faltar o texto ou a imagem."""
        options = {
            "opacity": self.opacity_spin.value(),
            "rotation": self.rotation_spin.value(),
            "position": self.position_combo.currentData(),
            "behind": self.behind_check.isChecked(),
        }
        if self.kind_combo.currentIndex() == 0:
            text = self.text_edit.text().strip()
            if not text:
                QMessageBox.warning(self, tr("Marca d'água"), tr("Digite o texto da marca d'água."))
                return None
            options.update(text=text, font_size=self.font_size_spin.value(), color=self.color_combo.color())
        else:
            image_path = self.image_picker.path()
            if not image_path:
                QMessageBox.warning(self, tr("Marca d'água"), tr("Escolha a imagem da marca d'água."))
                return None
            options.update(image_path=image_path, image_width=self.image_width_spin.value() / 100)
        return options

    def _preview(self):
        input_path = self.session.path()
        if not input_path:
            QMessageBox.warning(self, tr("Marca d'água"), tr("Abra um PDF para começar."))
            return
        options = self._options()
        if options is None:
            return

        def show(pdf_bytes: bytes):
            with PDFIUM_LOCK:
                document = pdfium.PdfDocument(pdf_bytes)
                page = document[0]
                width, height = page.get_size()
            try:
                scale = _PREVIEW_SIZE / max(width, height)
                self.preview_label.setPixmap(render_page(page, scale, self.devicePixelRatioF()))
            finally:
                with PDFIUM_LOCK:
                    page.close()
                    document.close()

        run_task(
            self,
            tr("Marca d'água"),
            call(watermark_preview, input_path, self.session.current_page(), **options),
            on_success=show,
            error_message=tr("Falha ao aplicar marca d'água: {error}"),
        )

    def _apply(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Marca d'água"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Marca d'água"), tr("Escolha o arquivo de saída."))
            return
        options = self._options()
        if options is None:
            return
        text = self.pages_edit.text()

        def task(_progress):
            pages = None
            if text.strip():
                pages = sorted(set(parse_page_ranges(text, len(open_reader(input_path, purpose=READ).pages))))
            AddWatermark().run(input_path, output_path, pages=pages, **options)

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(self, tr("Marca d'água"), tr("Marca d'água aplicada com sucesso."))

        run_task(
            self,
            tr("Marca d'água"),
            task,
            on_success=done,
            error_message=tr("Falha ao aplicar marca d'água: {error}"),
        )
