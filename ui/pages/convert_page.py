"""Aba de conversão entre PDF, imagens, documentos do Office e XML."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.convert import FIT_TO_IMAGE, ConvertFromImages, ConvertToImages
from core.office_convert import BASIC_SUFFIXES, SUPPORTED_SUFFIXES, ConvertOfficeToPDF, find_libreoffice
from core.xml_convert import ConvertXMLToPDF
from ui.i18n import tr, tr_message
from ui.tasks import call, call_with_progress, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_list_editor import FileListEditor
from ui.widgets.file_picker import FilePicker


class ConvertPage(QWidget):
    """Permite converter entre PDF e imagens, documentos do Office e PDF, e XML e PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(
            [
                tr("PDF para imagens"),
                tr("Imagens para PDF"),
                tr("Word/Excel/PowerPoint para PDF"),
                tr("XML para PDF"),
            ]
        )
        self.direction_combo.currentIndexChanged.connect(self._on_direction_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_to_images_widget())
        self.stack.addWidget(self._build_from_images_widget())
        self.stack.addWidget(self._build_office_widget())
        self.stack.addWidget(self._build_xml_widget())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Direção:")))
        layout.addWidget(self.direction_combo)
        layout.addWidget(self.stack)

    def _build_to_images_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pdf_source_bar = DocumentSourceBar(self.session)
        self.images_output_picker = FilePicker(mode="directory")
        convert_button = QPushButton(tr("Converter"))
        convert_button.clicked.connect(self._convert_to_images)

        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.pdf_source_bar)
        layout.addWidget(QLabel(tr("Pasta de saída das imagens:")))
        layout.addWidget(self.images_output_picker)
        layout.addWidget(convert_button)
        return widget

    def _build_from_images_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.image_list_editor = FileListEditor(
            dialog_caption=tr("Selecionar imagens"),
            file_filter="Imagens (*.png *.jpg *.jpeg *.bmp *.tiff *.webp)",
        )
        self.pdf_output_picker = FilePicker(
            mode="save",
            suggested_source=lambda: (self.image_list_editor.paths() or [None])[0],
            suggested_suffix="convertido",
        )
        self.image_page_size_combo = QComboBox()
        for label, value in (
            ("A4", "A4"),
            ("Carta (Letter)", "Letter"),
            ("Ofício (Legal)", "Legal"),
            ("Ajustar ao tamanho da imagem", FIT_TO_IMAGE),
        ):
            self.image_page_size_combo.addItem(tr(label), value)
        self.image_margin_spin = QDoubleSpinBox()
        self.image_margin_spin.setRange(0, 50)
        self.image_margin_spin.setSuffix(" mm")
        self.image_dpi_spin = QSpinBox()
        self.image_dpi_spin.setRange(50, 1200)
        self.image_dpi_spin.setValue(300)
        self.image_dpi_spin.setToolTip(tr("Resolução usada para calcular o tamanho da página a partir da imagem."))
        self.image_page_size_combo.currentIndexChanged.connect(self._update_image_dpi_state)
        self._update_image_dpi_state()

        options = QFormLayout()
        options.addRow(tr("Tamanho da página:"), self.image_page_size_combo)
        options.addRow(tr("Margem:"), self.image_margin_spin)
        options.addRow(tr("DPI da imagem:"), self.image_dpi_spin)

        convert_button = QPushButton(tr("Converter"))
        convert_button.clicked.connect(self._convert_from_images)

        layout.addWidget(QLabel(tr("Imagens (na ordem desejada):")))
        layout.addWidget(self.image_list_editor)
        layout.addLayout(options)
        layout.addWidget(QLabel(tr("Arquivo PDF de saída:")))
        layout.addWidget(self.pdf_output_picker)
        layout.addWidget(convert_button)
        return widget

    def _build_office_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        has_libreoffice = find_libreoffice() is not None
        suffixes = SUPPORTED_SUFFIXES if has_libreoffice else BASIC_SUFFIXES
        self.office_input_picker = FilePicker(
            mode="open",
            file_filter=tr("Documentos do Office") + " (" + " ".join(f"*{suffix}" for suffix in suffixes) + ")",
        )
        self.office_output_picker = FilePicker(
            mode="save",
            suggested_source=self.office_input_picker.path,
            suggested_suffix="convertido",
        )

        if has_libreoffice:
            engine_note = tr(
                "LibreOffice encontrado: a conversão preserva a formatação original e aceita "
                "também .doc, .xls, .ppt, .odt, .ods, .odp e .rtf."
            )
        else:
            engine_note = tr(
                "LibreOffice não encontrado: usando a conversão básica, que leva o texto, os "
                "títulos, as listas e as tabelas de arquivos .docx, .xlsx e .pptx, mas não a "
                "formatação visual exata, as imagens nem os cabeçalhos e rodapés."
            )
        engine_label = QLabel(engine_note)
        engine_label.setWordWrap(True)

        convert_button = QPushButton(tr("Converter"))
        convert_button.clicked.connect(self._convert_office)

        layout.addWidget(QLabel(tr("Arquivo Word, Excel ou PowerPoint de entrada:")))
        layout.addWidget(self.office_input_picker)
        layout.addWidget(QLabel(tr("Arquivo PDF de saída:")))
        layout.addWidget(self.office_output_picker)
        layout.addWidget(engine_label)
        layout.addWidget(convert_button)
        return widget

    def _build_xml_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.xml_input_picker = FilePicker(mode="open", file_filter="XML (*.xml)")
        self.xml_output_picker = FilePicker(
            mode="save", suggested_source=self.xml_input_picker.path, suggested_suffix="convertido"
        )
        self.xml_landscape_check = QCheckBox(tr("Páginas em paisagem (linhas mais longas)"))
        convert_button = QPushButton(tr("Converter"))
        convert_button.clicked.connect(self._convert_xml)

        layout.addWidget(QLabel(tr("Arquivo XML de entrada:")))
        layout.addWidget(self.xml_input_picker)
        layout.addWidget(QLabel(tr("Arquivo PDF de saída:")))
        layout.addWidget(self.xml_output_picker)
        layout.addWidget(self.xml_landscape_check)
        layout.addWidget(convert_button)
        return widget

    def _update_image_dpi_state(self):
        self.image_dpi_spin.setEnabled(self.image_page_size_combo.currentData() == FIT_TO_IMAGE)

    def _on_direction_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _convert_to_images(self):
        input_path = self.session.path()
        output_dir = self.images_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Converter"), tr("Abra um PDF para começar."))
            return
        if not output_dir:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha a pasta de saída."))
            return

        task = call_with_progress(ConvertToImages().run, input_path, output_dir)

        def done(output_paths):
            QMessageBox.information(
                self,
                tr("Converter"),
                tr("{count} imagem(ns) gerada(s) com sucesso.").format(count=len(output_paths)),
            )

        run_task(
            self,
            tr("Converter"),
            task,
            on_success=done,
            error_message=tr("Falha ao converter: {error}"),
        )

    def _convert_from_images(self):
        input_paths = self.image_list_editor.paths()
        output_path = self.pdf_output_picker.path()

        if not input_paths:
            QMessageBox.warning(self, tr("Converter"), tr("Adicione pelo menos uma imagem."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo PDF de saída."))
            return

        task = call_with_progress(
            ConvertFromImages().run,
            input_paths,
            output_path,
            page_size=self.image_page_size_combo.currentData(),
            margin_mm=self.image_margin_spin.value(),
            dpi=self.image_dpi_spin.value(),
        )

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(self, tr("Converter"), tr("PDF gerado com sucesso."))

        run_task(
            self,
            tr("Converter"),
            task,
            on_success=done,
            error_message=tr("Falha ao converter: {error}"),
        )

    def _convert_office(self):
        input_path = self.office_input_picker.path()
        output_path = self.office_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo PDF de saída."))
            return

        task = call_with_progress(ConvertOfficeToPDF().run, input_path, output_path)

        def done(result):
            self.session.open(output_path)
            message = tr("PDF gerado com sucesso.")
            if result.warnings:
                details = "\n".join("• " + tr_message(warning) for warning in result.warnings)
                message += "\n\n" + tr("A conversão básica deixou de fora:") + "\n" + details
            QMessageBox.information(self, tr("Converter"), message)

        run_task(
            self,
            tr("Converter"),
            task,
            on_success=done,
            error_message=tr("Falha ao converter: {error}"),
        )

    def _convert_xml(self):
        input_path = self.xml_input_picker.path()
        output_path = self.xml_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo XML de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo PDF de saída."))
            return

        task = call(
            ConvertXMLToPDF().run, input_path, output_path, landscape_pages=self.xml_landscape_check.isChecked()
        )

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(self, tr("Converter"), tr("PDF gerado com sucesso."))

        run_task(
            self,
            tr("Converter"),
            task,
            on_success=done,
            error_message=tr("Falha ao converter: {error}"),
        )
