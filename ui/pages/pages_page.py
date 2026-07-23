"""Aba de manipulação de páginas: rotação, reordenação e remoção."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.pages import RemovePages, ReorderPages, RotatePages
from ui.widgets.file_picker import FilePicker


def _parse_page_list(text: str) -> list[int]:
    text = text.strip()
    if not text:
        return []
    return [int(part.strip()) for part in text.split(",")]


class PagesPage(QWidget):
    """Permite rotacionar, reordenar ou remover páginas de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="save")

        self.operation_combo = QComboBox()
        self.operation_combo.addItems(["Rotacionar", "Reordenar", "Remover"])
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)

        self.rotate_angle_spin = QSpinBox()
        self.rotate_angle_spin.setRange(0, 359)
        self.rotate_angle_spin.setSingleStep(90)
        self.rotate_angle_spin.setValue(90)
        self.rotate_pages_edit = QLineEdit()
        self.rotate_pages_edit.setPlaceholderText("Páginas (vazio = todas), ex: 0,2")

        self.reorder_edit = QLineEdit()
        self.reorder_edit.setPlaceholderText("Nova ordem das páginas, ex: 2,0,1")

        self.remove_edit = QLineEdit()
        self.remove_edit.setPlaceholderText("Páginas a remover, ex: 1,3")

        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_rotate_widget())
        self.params_stack.addWidget(self._build_simple_widget("Nova ordem:", self.reorder_edit))
        self.params_stack.addWidget(self._build_simple_widget("Páginas a remover:", self.remove_edit))

        apply_button = QPushButton("Aplicar")
        apply_button.clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel("Operação:"))
        layout.addWidget(self.operation_combo)
        layout.addWidget(self.params_stack)
        layout.addWidget(apply_button)

    def _build_rotate_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Ângulo:"))
        layout.addWidget(self.rotate_angle_spin)
        layout.addWidget(QLabel("Páginas a rotacionar:"))
        layout.addWidget(self.rotate_pages_edit)
        return widget

    def _build_simple_widget(self, label_text: str, field: QLineEdit) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label_text))
        layout.addWidget(field)
        return widget

    def _on_operation_changed(self, index: int):
        self.params_stack.setCurrentIndex(index)

    def _apply(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Páginas", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Páginas", "Escolha o arquivo de saída.")
            return

        operation = self.operation_combo.currentText()

        try:
            if operation == "Rotacionar":
                pages = _parse_page_list(self.rotate_pages_edit.text()) or None
                RotatePages().run(
                    input_path, output_path, angle=self.rotate_angle_spin.value(), pages=pages
                )
            elif operation == "Reordenar":
                order = _parse_page_list(self.reorder_edit.text())
                if not order:
                    QMessageBox.warning(self, "Páginas", "Informe a nova ordem das páginas.")
                    return
                ReorderPages().run(input_path, output_path, order=order)
            else:
                pages = _parse_page_list(self.remove_edit.text())
                if not pages:
                    QMessageBox.warning(self, "Páginas", "Informe quais páginas remover.")
                    return
                RemovePages().run(input_path, output_path, pages=pages)
        except Exception as exc:
            QMessageBox.critical(self, "Páginas", f"Falha ao processar: {exc}")
            return

        QMessageBox.information(self, "Páginas", "Operação concluída com sucesso.")
