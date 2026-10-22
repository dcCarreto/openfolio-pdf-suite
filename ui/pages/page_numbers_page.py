"""Aba de numeração de páginas de PDFs."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from core.fonts import MONO, SANS, SANS_BOLD
from core.page_numbers import AddBatesNumbers, AddHeaderFooter, AddPageNumbers
from ui.i18n import tr
from ui.page_ranges import format_page_ranges, parse_page_ranges
from ui.tasks import call, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_BATES_POSITION_LABELS = [
    ("Inferior direito", "bottom-right"),
    ("Inferior esquerdo", "bottom-left"),
    ("Superior direito", "top-right"),
    ("Superior esquerdo", "top-left"),
]

_HF_POSITION_LABELS = [
    ("Cabeçalho à esquerda", "header-left"),
    ("Cabeçalho ao centro", "header-center"),
    ("Cabeçalho à direita", "header-right"),
    ("Rodapé à esquerda", "footer-left"),
    ("Rodapé ao centro", "footer-center"),
    ("Rodapé à direita", "footer-right"),
]


_NUMBER_STYLES = [
    ("Arábicos (1, 2, 3)", "arabic"),
    ("Romanos minúsculos (i, ii, iii)", "roman"),
    ("Romanos maiúsculos (I, II, III)", "ROMAN"),
]

_FONTS = [("Sem serifa", SANS), ("Sem serifa, negrito", SANS_BOLD), ("Monoespaçada", MONO)]


class PageNumbersPage(QWidget):
    """Permite adicionar números de página no rodapé de um PDF, ou numeração Bates
    (prefixo + sequência global) usada em processos jurídicos."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [tr("Numeração de página"), tr("Numeração Bates"), tr("Cabeçalho/Rodapé")]
        )
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_numbers_panel())
        self.stack.addWidget(self._build_bates_panel())
        self.stack.addWidget(self._build_header_footer_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_page_numbers_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="numerado"
        )

        self.start_at_spin = QSpinBox()
        self.start_at_spin.setRange(0, 9999)
        self.start_at_spin.setValue(1)

        self.number_style_combo = QComboBox()
        for label, value in _NUMBER_STYLES:
            self.number_style_combo.addItem(tr(label), value)
        self.page_labels_check = QCheckBox(tr("Usar os rótulos de página do documento"))
        self.page_labels_check.setToolTip(
            tr("Escreve o número que o visualizador mostra para cada página (como iii ou A-1), em vez de contar.")
        )
        self.page_labels_check.toggled.connect(self._update_number_state)

        self.number_position_combo = QComboBox()
        for label, value in _HF_POSITION_LABELS:
            self.number_position_combo.addItem(tr(label), value)
        self.number_position_combo.setCurrentIndex(self.number_position_combo.findData("footer-center"))

        self.skip_first_spin = QSpinBox()
        self.skip_first_spin.setRange(0, 9999)
        self.skip_first_spin.setToolTip(tr("A capa e as páginas de abertura ficam sem número; a contagem começa depois delas."))

        self.number_pages_edit = QLineEdit()
        self.number_pages_edit.setPlaceholderText(tr("Páginas (vazio = todas), ex: 1, 3-5"))
        self.number_selection_button = QPushButton(tr("Usar seleção"))
        self.number_selection_button.setToolTip(
            tr("Preenche com as páginas selecionadas nas miniaturas (Ctrl ou Shift + clique).")
        )
        self.number_selection_button.clicked.connect(
            lambda: self.number_pages_edit.setText(format_page_ranges(self.session.selected_pages()))
        )
        pages_row = QHBoxLayout()
        pages_row.addWidget(self.number_pages_edit, 1)
        pages_row.addWidget(self.number_selection_button)

        self.number_font_combo = QComboBox()
        for label, value in _FONTS:
            self.number_font_combo.addItem(tr(label), value)
        self.number_font_size_spin = QSpinBox()
        self.number_font_size_spin.setRange(6, 72)
        self.number_font_size_spin.setValue(10)

        options = QFormLayout()
        options.addRow(tr("Começar em:"), self.start_at_spin)
        options.addRow(tr("Algarismos:"), self.number_style_combo)
        options.addRow("", self.page_labels_check)
        options.addRow(tr("Posição:"), self.number_position_combo)
        options.addRow(tr("Pular as primeiras:"), self.skip_first_spin)
        options.addRow(tr("Páginas:"), pages_row)
        options.addRow(tr("Fonte:"), self.number_font_combo)
        options.addRow(tr("Tamanho da fonte:"), self.number_font_size_spin)

        apply_button = QPushButton(tr("Adicionar numeração"))
        apply_button.clicked.connect(self._apply)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addLayout(options)
        layout.addWidget(apply_button)
        return widget

    def _update_number_state(self):
        counting = not self.page_labels_check.isChecked()
        self.start_at_spin.setEnabled(counting)
        self.number_style_combo.setEnabled(counting)

    def _build_bates_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.bates_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="bates"
        )
        self.bates_prefix_edit = QLineEdit()
        self.bates_prefix_edit.setPlaceholderText(tr("Prefixo (ex.: CASO-)"))

        self.bates_start_at_spin = QSpinBox()
        self.bates_start_at_spin.setRange(0, 999_999_999)
        self.bates_start_at_spin.setValue(1)

        self.bates_digits_spin = QSpinBox()
        self.bates_digits_spin.setRange(1, 12)
        self.bates_digits_spin.setValue(6)

        self.bates_position_combo = QComboBox()
        for label, _value in _BATES_POSITION_LABELS:
            self.bates_position_combo.addItem(tr(label))

        apply_button = QPushButton(tr("Adicionar numeração Bates"))
        apply_button.clicked.connect(self._apply_bates)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.bates_output_picker)
        layout.addWidget(QLabel(tr("Prefixo:")))
        layout.addWidget(self.bates_prefix_edit)
        layout.addWidget(QLabel(tr("Começar em:")))
        layout.addWidget(self.bates_start_at_spin)
        layout.addWidget(QLabel(tr("Dígitos (zeros à esquerda):")))
        layout.addWidget(self.bates_digits_spin)
        layout.addWidget(QLabel(tr("Posição:")))
        layout.addWidget(self.bates_position_combo)
        layout.addWidget(apply_button)
        return widget

    def _build_header_footer_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr("Suporta os textos {page} (número da página) e {pages} (total de páginas).")
        )
        note.setWordWrap(True)

        self.hf_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="com_cabecalho"
        )
        self.hf_text_edit = QLineEdit()
        self.hf_text_edit.setPlaceholderText(tr("Texto, ex: Página {page} de {pages}"))

        self.hf_position_combo = QComboBox()
        for label, _value in _HF_POSITION_LABELS:
            self.hf_position_combo.addItem(tr(label))

        apply_button = QPushButton(tr("Adicionar cabeçalho/rodapé"))
        apply_button.clicked.connect(self._apply_header_footer)

        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.hf_output_picker)
        layout.addWidget(QLabel(tr("Texto:")))
        layout.addWidget(self.hf_text_edit)
        layout.addWidget(QLabel(tr("Posição:")))
        layout.addWidget(self.hf_position_combo)
        layout.addWidget(apply_button)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _apply(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Numeração de páginas"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Numeração de páginas"), tr("Escolha o arquivo de saída."))
            return

        text = self.number_pages_edit.text()
        options = {
            "start_at": self.start_at_spin.value(),
            "font_size": self.number_font_size_spin.value(),
            "position": self.number_position_combo.currentData(),
            "style": self.number_style_combo.currentData(),
            "skip_first": self.skip_first_spin.value(),
            "use_page_labels": self.page_labels_check.isChecked(),
            "font": self.number_font_combo.currentData(),
        }

        def task(_progress):
            pages = None
            if text.strip():
                pages = sorted(set(parse_page_ranges(text, len(open_reader(input_path, purpose=READ).pages))))
            AddPageNumbers().run(input_path, output_path, pages=pages, **options)

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(
                self, tr("Numeração de páginas"), tr("Numeração adicionada com sucesso.")
            )

        run_task(
            self,
            tr("Numeração de páginas"),
            task,
            on_success=done,
            error_message=tr("Falha ao numerar páginas: {error}"),
        )

    def _apply_bates(self):
        input_path = self.session.path()
        output_path = self.bates_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Numeração Bates"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Numeração Bates"), tr("Escolha o arquivo de saída."))
            return

        position = _BATES_POSITION_LABELS[self.bates_position_combo.currentIndex()][1]

        task = call(
            AddBatesNumbers().run,
            input_path,
            output_path,
            prefix=self.bates_prefix_edit.text(),
            start_at=self.bates_start_at_spin.value(),
            digits=self.bates_digits_spin.value(),
            position=position,
        )

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(
                self, tr("Numeração Bates"), tr("Numeração Bates adicionada com sucesso.")
            )

        run_task(
            self,
            tr("Numeração Bates"),
            task,
            on_success=done,
            error_message=tr("Falha ao adicionar numeração Bates: {error}"),
        )

    def _apply_header_footer(self):
        input_path = self.session.path()
        output_path = self.hf_output_picker.path()
        text = self.hf_text_edit.text()

        if not input_path:
            QMessageBox.warning(self, tr("Cabeçalho/Rodapé"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Cabeçalho/Rodapé"), tr("Escolha o arquivo de saída."))
            return
        if not text:
            QMessageBox.warning(self, tr("Cabeçalho/Rodapé"), tr("Digite o texto do cabeçalho/rodapé."))
            return

        position = _HF_POSITION_LABELS[self.hf_position_combo.currentIndex()][1]

        task = call(AddHeaderFooter().run, input_path, output_path, text=text, position=position)

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(
                self, tr("Cabeçalho/Rodapé"), tr("Cabeçalho/rodapé adicionado com sucesso.")
            )

        run_task(
            self,
            tr("Cabeçalho/Rodapé"),
            task,
            on_success=done,
            error_message=tr("Falha ao adicionar cabeçalho/rodapé: {error}"),
        )
