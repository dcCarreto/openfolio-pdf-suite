"""Aba de manipulação de páginas: rotação, reordenação, remoção, inserção e substituição.

As páginas são contadas a partir de 1, como no visualizador; a conversão para os índices
de `core/pages.py` acontece em `ui/page_ranges.py`.
"""

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

from core.base import READ, open_reader
from core.pages import InsertPages, RemovePages, ReorderPages, ReplacePages, RotatePages
from ui.i18n import tr
from ui.page_ranges import parse_page_ranges
from ui.tasks import run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_OPERATIONS = ["Rotacionar", "Reordenar", "Remover", "Inserir", "Substituir"]
_ROTATIONS = [("90° no sentido horário", 90), ("180°", 180), ("90° no sentido anti-horário", 270)]


def _page_count(path: str | None) -> int | None:
    if not path:
        return None
    try:
        return len(open_reader(path, purpose=READ).pages)
    except Exception:
        return None


class PagesPage(QWidget):
    """Permite rotacionar, reordenar, remover, inserir ou substituir páginas de um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(mode="save", suggested_source=session.path)

        self.operation_combo = QComboBox()
        self.operation_combo.addItems([tr(op) for op in _OPERATIONS])
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)

        self.rotate_angle_combo = QComboBox()
        self.rotate_angle_combo.addItems([tr(label) for label, _angle in _ROTATIONS])
        self.rotate_pages_edit = QLineEdit()
        self.rotate_pages_edit.setPlaceholderText(tr("Páginas (vazio = todas), ex: 1, 3-5"))

        self.reorder_edit = QLineEdit()
        self.reorder_edit.setPlaceholderText(tr("Todas as páginas na nova ordem, ex: 3, 1, 2 ou 4-1"))

        self.remove_edit = QLineEdit()
        self.remove_edit.setPlaceholderText(tr("Páginas a remover, ex: 2, 5-7"))

        self.insert_source_picker = FilePicker(mode="open")
        self.insert_at_spin = QSpinBox()
        self.insert_at_spin.setRange(1, 100000)

        self.replace_source_picker = FilePicker(mode="open")
        self.replace_start_spin = QSpinBox()
        self.replace_start_spin.setRange(1, 100000)
        self.replace_end_spin = QSpinBox()
        self.replace_end_spin.setRange(1, 100000)

        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_rotate_widget())
        self.params_stack.addWidget(self._build_simple_widget(tr("Nova ordem:"), self.reorder_edit))
        self.params_stack.addWidget(
            self._build_simple_widget(tr("Páginas a remover:"), self.remove_edit)
        )
        self.params_stack.addWidget(self._build_insert_widget())
        self.params_stack.addWidget(self._build_replace_widget())

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
        layout.addWidget(self.rotate_angle_combo)
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

    def _build_insert_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(tr("PDF com as páginas a inserir:")))
        layout.addWidget(self.insert_source_picker)
        layout.addWidget(QLabel(tr("Inserir antes da página (total + 1 = no fim):")))
        layout.addWidget(self.insert_at_spin)
        return widget

    def _build_replace_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(tr("PDF com as páginas substitutas:")))
        layout.addWidget(self.replace_source_picker)
        layout.addWidget(QLabel(tr("Substituir da página:")))
        layout.addWidget(self.replace_start_spin)
        layout.addWidget(QLabel(tr("Até a página (inclusive):")))
        layout.addWidget(self.replace_end_spin)
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
        total_pages = _page_count(input_path)

        try:
            if operation == "Rotacionar":
                text = self.rotate_pages_edit.text()
                pages = sorted(set(parse_page_ranges(text, total_pages))) if text.strip() else None
                angle = _ROTATIONS[self.rotate_angle_combo.currentIndex()][1]
                action = lambda: RotatePages().run(input_path, output_path, angle=angle, pages=pages)  # noqa: E731
            elif operation == "Reordenar":
                order = parse_page_ranges(self.reorder_edit.text(), total_pages)
                if not order:
                    QMessageBox.warning(self, tr("Páginas"), tr("Informe a nova ordem das páginas."))
                    return
                action = lambda: ReorderPages().run(input_path, output_path, order=order)  # noqa: E731
            elif operation == "Remover":
                pages = sorted(set(parse_page_ranges(self.remove_edit.text(), total_pages)))
                if not pages:
                    QMessageBox.warning(self, tr("Páginas"), tr("Informe quais páginas remover."))
                    return
                action = lambda: RemovePages().run(input_path, output_path, pages=pages)  # noqa: E731
            else:
                source_picker = (
                    self.insert_source_picker if operation == "Inserir" else self.replace_source_picker
                )
                source_path = source_picker.path()
                if not source_path:
                    QMessageBox.warning(self, tr("Páginas"), tr("Escolha o PDF de origem das páginas."))
                    return
                if operation == "Inserir":
                    at_index = self.insert_at_spin.value() - 1
                    action = lambda: InsertPages().run(input_path, output_path, source_path, at_index=at_index)  # noqa: E731
                else:
                    start_index = self.replace_start_spin.value() - 1
                    end_index = self.replace_end_spin.value()  # "até" inclusivo = fim exclusivo
                    action = lambda: ReplacePages().run(  # noqa: E731
                        input_path, output_path, source_path, start_index=start_index, end_index=end_index
                    )
        except ValueError as exc:
            QMessageBox.warning(self, tr("Páginas"), str(exc))
            return

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(self, tr("Páginas"), tr("Operação concluída com sucesso."))

        # As variáveis capturadas por `action` já são valores lidos dos widgets aqui, na
        # thread da interface.
        run_task(self, tr("Páginas"), lambda _progress: action(), on_success=done)
