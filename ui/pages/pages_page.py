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
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_OPERATIONS = ["Rotacionar", "Reordenar", "Remover"]


def _parse_page_list(text: str) -> list[int]:
    text = text.strip()
    if not text:
        return []
    return [int(part.strip()) for part in text.split(",")]


class PagesPage(QWidget):
    """Permite rotacionar, reordenar ou remover páginas de um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(mode="save", suggested_source=session.path)

        self.operation_combo = QComboBox()
        self.operation_combo.addItems([tr(op) for op in _OPERATIONS])
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)

        self.rotate_angle_spin = QSpinBox()
        self.rotate_angle_spin.setRange(0, 359)
        self.rotate_angle_spin.setSingleStep(90)
        self.rotate_angle_spin.setValue(90)
        self.rotate_pages_edit = QLineEdit()
        self.rotate_pages_edit.setPlaceholderText(tr("Páginas (vazio = todas), ex: 0,2"))

        self.reorder_edit = QLineEdit()
        self.reorder_edit.setPlaceholderText(tr("Nova ordem das páginas, ex: 2,0,1"))

        self.remove_edit = QLineEdit()
        self.remove_edit.setPlaceholderText(tr("Páginas a remover, ex: 1,3"))

        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_rotate_widget())
        self.params_stack.addWidget(self._build_simple_widget(tr("Nova ordem:"), self.reorder_edit))
        self.params_stack.addWidget(
            self._build_simple_widget(tr("Páginas a remover:"), self.remove_edit)
        )

        apply_button = QPushButton(tr("Aplicar"))
        apply_button.clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Operação:")))
        layout.addWidget(self.operation_combo)
        layout.addWidget(self.params_stack)
        layout.addWidget(apply_button)

    def _build_rotate_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(tr("Ângulo:")))
        layout.addWidget(self.rotate_angle_spin)
        layout.addWidget(QLabel(tr("Páginas a rotacionar:")))
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
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Páginas"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Páginas"), tr("Escolha o arquivo de saída."))
            return

        operation = _OPERATIONS[self.operation_combo.currentIndex()]
        field_by_operation = {
            "Rotacionar": self.rotate_pages_edit,
            "Reordenar": self.reorder_edit,
            "Remover": self.remove_edit,
        }

        try:
            pages = _parse_page_list(field_by_operation[operation].text())
        except ValueError:
            QMessageBox.warning(
                self,
                tr("Páginas"),
                tr("Lista de páginas inválida. Use números separados por vírgula, ex: 0,2."),
            )
            return

        if operation == "Reordenar" and not pages:
            QMessageBox.warning(self, tr("Páginas"), tr("Informe a nova ordem das páginas."))
            return
        if operation == "Remover" and not pages:
            QMessageBox.warning(self, tr("Páginas"), tr("Informe quais páginas remover."))
            return

        try:
            if operation == "Rotacionar":
                RotatePages().run(
                    input_path, output_path, angle=self.rotate_angle_spin.value(), pages=pages or None
                )
            elif operation == "Reordenar":
                ReorderPages().run(input_path, output_path, order=pages)
            else:
                RemovePages().run(input_path, output_path, pages=pages)
        except IndexError:
            QMessageBox.warning(
                self, tr("Páginas"), tr("Uma das páginas informadas não existe neste PDF.")
            )
            return
        except Exception as exc:
            QMessageBox.critical(self, tr("Páginas"), tr("Falha ao processar: {error}").format(error=exc))
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Páginas"), tr("Operação concluída com sucesso."))
