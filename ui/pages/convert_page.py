"""Aba de conversão entre PDF, imagens, documentos do Office e XML."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.convert import ConvertFromImages, ConvertToImages
from core.office_convert import ConvertOfficeToPDF, find_libreoffice
from core.xml_convert import ConvertXMLToPDF
from ui.i18n import tr
from ui.widgets.file_list_editor import FileListEditor
from ui.widgets.file_picker import FilePicker


class ConvertPage(QWidget):
    """Permite converter entre PDF e imagens, documentos do Office e PDF, e XML e PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

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

        self.pdf_input_picker = FilePicker(mode="open")
        self.images_output_picker = FilePicker(mode="directory")
        convert_button = QPushButton(tr("Converter"))
        convert_button.clicked.connect(self._convert_to_images)

        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.pdf_input_picker)
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
        self.pdf_output_picker = FilePicker(mode="save")
        convert_button = QPushButton(tr("Converter"))
        convert_button.clicked.connect(self._convert_from_images)

        layout.addWidget(QLabel(tr("Imagens (na ordem desejada):")))
        layout.addWidget(self.image_list_editor)
        layout.addWidget(QLabel(tr("Arquivo PDF de saída:")))
        layout.addWidget(self.pdf_output_picker)
        layout.addWidget(convert_button)
        return widget

    def _build_office_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.office_input_picker = FilePicker(
            mode="open", file_filter="Documentos do Office (*.docx *.xlsx *.xls *.pptx)"
        )
        self.office_output_picker = FilePicker(mode="save")

        if find_libreoffice():
            engine_note = tr("LibreOffice encontrado: a conversão preserva a formatação original.")
        else:
            engine_note = tr(
                "LibreOffice não encontrado: usando conversão básica em Python "
                "(preserva texto, mas não a formatação visual exata)."
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
        self.xml_output_picker = FilePicker(mode="save")
        convert_button = QPushButton(tr("Converter"))
        convert_button.clicked.connect(self._convert_xml)

        layout.addWidget(QLabel(tr("Arquivo XML de entrada:")))
        layout.addWidget(self.xml_input_picker)
        layout.addWidget(QLabel(tr("Arquivo PDF de saída:")))
        layout.addWidget(self.xml_output_picker)
        layout.addWidget(convert_button)
        return widget

    def _on_direction_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _convert_to_images(self):
        input_path = self.pdf_input_picker.path()
        output_dir = self.images_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo PDF de entrada."))
            return
        if not output_dir:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha a pasta de saída."))
            return

        try:
            output_paths = ConvertToImages().run(input_path, output_dir)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Converter"), tr("Falha ao converter: {error}").format(error=exc)
            )
            return

        QMessageBox.information(
            self,
            tr("Converter"),
            tr("{count} imagem(ns) gerada(s) com sucesso.").format(count=len(output_paths)),
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

        try:
            ConvertFromImages().run(input_paths, output_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Converter"), tr("Falha ao converter: {error}").format(error=exc)
            )
            return

        QMessageBox.information(self, tr("Converter"), tr("PDF gerado com sucesso."))

    def _convert_office(self):
        input_path = self.office_input_picker.path()
        output_path = self.office_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo PDF de saída."))
            return

        try:
            ConvertOfficeToPDF().run(input_path, output_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Converter"), tr("Falha ao converter: {error}").format(error=exc)
            )
            return

        QMessageBox.information(self, tr("Converter"), tr("PDF gerado com sucesso."))

    def _convert_xml(self):
        input_path = self.xml_input_picker.path()
        output_path = self.xml_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo XML de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Converter"), tr("Escolha o arquivo PDF de saída."))
            return

        try:
            ConvertXMLToPDF().run(input_path, output_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Converter"), tr("Falha ao converter: {error}").format(error=exc)
            )
            return

        QMessageBox.information(self, tr("Converter"), tr("PDF gerado com sucesso."))
