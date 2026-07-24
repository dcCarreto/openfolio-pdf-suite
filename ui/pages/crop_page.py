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
from ui.i18n import tr
from ui.page_sizes import CUSTOM_SIZE_LABEL, PAGE_SIZES
from ui.widgets.file_picker import FilePicker

_SIZE_LABELS = [*PAGE_SIZES.keys(), CUSTOM_SIZE_LABEL]


class CropPage(QWidget):
    """Permite cortar margens ou redimensionar as páginas de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Cortar margens"), tr("Redimensionar")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_crop_panel())
        self.stack.addWidget(self._build_scale_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Operação:")))
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
        margins_layout.addWidget(QLabel(tr("Esquerda:")))
        margins_layout.addWidget(self.left_spin)
        margins_layout.addWidget(QLabel(tr("Baixo:")))
        margins_layout.addWidget(self.bottom_spin)
        margins_layout.addWidget(QLabel(tr("Direita:")))
        margins_layout.addWidget(self.right_spin)
        margins_layout.addWidget(QLabel(tr("Topo:")))
        margins_layout.addWidget(self.top_spin)

        apply_button = QPushButton(tr("Cortar"))
        apply_button.clicked.connect(self._crop)

        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.crop_input_picker)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.crop_output_picker)
        layout.addWidget(QLabel(tr("Margens a cortar (pontos):")))
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
        self.scale_size_combo.addItems([tr(label) for label in _SIZE_LABELS])
        self.scale_size_combo.currentIndexChanged.connect(self._on_scale_size_changed)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 20000)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1, 20000)
        self._on_scale_size_changed(self.scale_size_combo.currentIndex())

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel(tr("Tamanho:")))
        size_layout.addWidget(self.scale_size_combo)
        size_layout.addWidget(QLabel(tr("Largura:")))
        size_layout.addWidget(self.width_spin)
        size_layout.addWidget(QLabel(tr("Altura:")))
        size_layout.addWidget(self.height_spin)

        apply_button = QPushButton(tr("Redimensionar"))
        apply_button.clicked.connect(self._scale)

        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.scale_input_picker)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.scale_output_picker)
        layout.addWidget(QLabel(tr("Novo tamanho da página (pontos):")))
        layout.addLayout(size_layout)
        layout.addWidget(apply_button)
        return widget

    def _on_scale_size_changed(self, index: int):
        label = _SIZE_LABELS[index]
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
            QMessageBox.warning(self, tr("Cortar"), tr("Escolha o arquivo de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Cortar"), tr("Escolha o arquivo de saída."))
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
            QMessageBox.critical(
                self, tr("Cortar"), tr("Falha ao cortar páginas: {error}").format(error=exc)
            )
            return

        QMessageBox.information(self, tr("Cortar"), tr("Páginas cortadas com sucesso."))

    def _scale(self):
        input_path = self.scale_input_picker.path()
        output_path = self.scale_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Redimensionar"), tr("Escolha o arquivo de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Redimensionar"), tr("Escolha o arquivo de saída."))
            return

        try:
            ScalePages().run(
                input_path,
                output_path,
                width=self.width_spin.value(),
                height=self.height_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("Redimensionar"),
                tr("Falha ao redimensionar páginas: {error}").format(error=exc),
            )
            return

        QMessageBox.information(self, tr("Redimensionar"), tr("Páginas redimensionadas com sucesso."))
