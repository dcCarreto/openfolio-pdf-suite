"""Aba de conversão entre PDF e imagens."""

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
from ui.widgets.file_list_editor import FileListEditor
from ui.widgets.file_picker import FilePicker


class ConvertPage(QWidget):
    """Permite converter páginas de um PDF em imagens, ou imagens em um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["PDF para imagens", "Imagens para PDF"])
        self.direction_combo.currentIndexChanged.connect(self._on_direction_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_to_images_widget())
        self.stack.addWidget(self._build_from_images_widget())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Direção:"))
        layout.addWidget(self.direction_combo)
        layout.addWidget(self.stack)

    def _build_to_images_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pdf_input_picker = FilePicker(mode="open")
        self.images_output_picker = FilePicker(mode="directory")
        convert_button = QPushButton("Converter")
        convert_button.clicked.connect(self._convert_to_images)

        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.pdf_input_picker)
        layout.addWidget(QLabel("Pasta de saída das imagens:"))
        layout.addWidget(self.images_output_picker)
        layout.addWidget(convert_button)
        return widget

    def _build_from_images_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.image_list_editor = FileListEditor(
            dialog_caption="Selecionar imagens",
            file_filter="Imagens (*.png *.jpg *.jpeg *.bmp *.tiff *.webp)",
        )
        self.pdf_output_picker = FilePicker(mode="save")
        convert_button = QPushButton("Converter")
        convert_button.clicked.connect(self._convert_from_images)

        layout.addWidget(QLabel("Imagens (na ordem desejada):"))
        layout.addWidget(self.image_list_editor)
        layout.addWidget(QLabel("Arquivo PDF de saída:"))
        layout.addWidget(self.pdf_output_picker)
        layout.addWidget(convert_button)
        return widget

    def _on_direction_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _convert_to_images(self):
        input_path = self.pdf_input_picker.path()
        output_dir = self.images_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Converter", "Escolha o arquivo PDF de entrada.")
            return
        if not output_dir:
            QMessageBox.warning(self, "Converter", "Escolha a pasta de saída.")
            return

        try:
            output_paths = ConvertToImages().run(input_path, output_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Converter", f"Falha ao converter: {exc}")
            return

        QMessageBox.information(
            self, "Converter", f"{len(output_paths)} imagem(ns) gerada(s) com sucesso."
        )

    def _convert_from_images(self):
        input_paths = self.image_list_editor.paths()
        output_path = self.pdf_output_picker.path()

        if not input_paths:
            QMessageBox.warning(self, "Converter", "Adicione pelo menos uma imagem.")
            return
        if not output_path:
            QMessageBox.warning(self, "Converter", "Escolha o arquivo PDF de saída.")
            return

        try:
            ConvertFromImages().run(input_paths, output_path)
        except Exception as exc:
            QMessageBox.critical(self, "Converter", f"Falha ao converter: {exc}")
            return

        QMessageBox.information(self, "Converter", "PDF gerado com sucesso.")
