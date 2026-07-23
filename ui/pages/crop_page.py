"""Aba de corte e redimensionamento de páginas de PDFs."""

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.crop import CropPages, ScalePages
from ui.page_sizes import CUSTOM_SIZE_LABEL, PAGE_SIZES
from ui.widgets.file_picker import FilePicker


class CropPage(QWidget):
    """Permite cortar margens ou redimensionar as páginas de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Cortar margens", "Redimensionar"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_crop_panel())
        self.stack.addWidget(self._build_scale_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Operação:"))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_crop_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.crop_input_picker = FilePicker(mode="open")
        self.crop_output_picker = FilePicker(mode="save")

        self.left_spin = self._margin_spin()
        self.bottom_spin = self._margin_spin()
        self.right_spin = self._margin_spin()
        self.top_spin = self._margin_spin()

        margins_layout = QHBoxLayout()
        margins_layout.addWidget(QLabel("Esquerda:"))
        margins_layout.addWidget(self.left_spin)
        margins_layout.addWidget(QLabel("Baixo:"))
        margins_layout.addWidget(self.bottom_spin)
        margins_layout.addWidget(QLabel("Direita:"))
        margins_layout.addWidget(self.right_spin)
        margins_layout.addWidget(QLabel("Topo:"))
        margins_layout.addWidget(self.top_spin)

        apply_button = QPushButton("Cortar")
        apply_button.clicked.connect(self._crop)

        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.crop_input_picker)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.crop_output_picker)
        layout.addWidget(QLabel("Margens a cortar (pontos):"))
        layout.addLayout(margins_layout)
        layout.addWidget(apply_button)
        return widget

    def _build_scale_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scale_input_picker = FilePicker(mode="open")
        self.scale_output_picker = FilePicker(mode="save")

        self.scale_size_combo = QComboBox()
        self.scale_size_combo.addItems([*PAGE_SIZES.keys(), CUSTOM_SIZE_LABEL])
        self.scale_size_combo.currentTextChanged.connect(self._on_scale_size_changed)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 20000)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1, 20000)
        self._on_scale_size_changed(self.scale_size_combo.currentText())

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Tamanho:"))
        size_layout.addWidget(self.scale_size_combo)
        size_layout.addWidget(QLabel("Largura:"))
        size_layout.addWidget(self.width_spin)
        size_layout.addWidget(QLabel("Altura:"))
        size_layout.addWidget(self.height_spin)

        apply_button = QPushButton("Redimensionar")
        apply_button.clicked.connect(self._scale)

        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.scale_input_picker)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.scale_output_picker)
        layout.addWidget(QLabel("Novo tamanho da página (pontos):"))
        layout.addLayout(size_layout)
        layout.addWidget(apply_button)
        return widget

    def _on_scale_size_changed(self, label: str):
        is_custom = label == CUSTOM_SIZE_LABEL
        self.width_spin.setEnabled(is_custom)
        self.height_spin.setEnabled(is_custom)
        if not is_custom:
            width, height = PAGE_SIZES[label]
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)

    def _margin_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 5000)
        spin.setValue(0)
        return spin

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _crop(self):
        input_path = self.crop_input_picker.path()
        output_path = self.crop_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Cortar", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Cortar", "Escolha o arquivo de saída.")
            return

        try:
            CropPages().run(
                input_path,
                output_path,
                left=self.left_spin.value(),
                bottom=self.bottom_spin.value(),
                right=self.right_spin.value(),
                top=self.top_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Cortar", f"Falha ao cortar páginas: {exc}")
            return

        QMessageBox.information(self, "Cortar", "Páginas cortadas com sucesso.")

    def _scale(self):
        input_path = self.scale_input_picker.path()
        output_path = self.scale_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Redimensionar", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Redimensionar", "Escolha o arquivo de saída.")
            return

        try:
            ScalePages().run(
                input_path,
                output_path,
                width=self.width_spin.value(),
                height=self.height_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Redimensionar", f"Falha ao redimensionar páginas: {exc}")
            return

        QMessageBox.information(self, "Redimensionar", "Páginas redimensionadas com sucesso.")
