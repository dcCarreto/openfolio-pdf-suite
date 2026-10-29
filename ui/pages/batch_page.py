"""Aba Processar em lote (A05): a mesma operação em todos os PDFs de uma pasta.

Os resultados vão para outra pasta (por padrão, "processados" dentro da pasta de entrada),
com o sufixo da operação no nome; nada é gravado por cima. Ao terminar, a tabela mostra o
resultado de cada arquivo e um relatório em CSV fica na pasta de saída.
"""

import os

from PySide6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.batch import BatchProcess, pdfs_in_folder
from core.compress import CompressPDF
from core.ocr import OCRDocument, find_tesseract, get_available_languages
from core.page_numbers import AddPageNumbers
from core.pdfa import ConvertToPDFA
from core.protect import ProtectPDF
from core.tabular import write_table
from core.watermark import AddWatermark
from ui.errors import describe_error
from ui.i18n import error_text, tr
from ui.pages.compress_page import _LEVELS
from ui.pages.ocr_page import _LANGUAGE_NAMES
from ui.tasks import run_task
from ui.widget_state import clear_passwords
from ui.widgets.file_picker import FilePicker

# (rótulo, sufixo do arquivo de saída)
_OPERATIONS = [
    ("Comprimir", "comprimido"),
    ("OCR", "ocr"),
    ("Marca d'água", "marca_dagua"),
    ("Numerar páginas", "numerado"),
    ("Proteger com senha", "protegido"),
    ("Converter para PDF/A-2b", "pdfa"),
]
_COMPRESS, _OCR, _WATERMARK, _NUMBERS, _PROTECT, _PDFA = range(len(_OPERATIONS))
REPORT_NAME = "relatorio_lote.csv"


def _breakable(path: str) -> str:
    """Caminho que pode quebrar linha depois de cada barra: um caminho longo sem espaços
    alargava o painel inteiro."""
    return path.replace(os.sep, os.sep + "\u200b")


class BatchPage(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.input_picker = FilePicker(mode="directory")
        self.input_picker.path_changed.connect(self._update_found)
        self.found_label = QLabel()
        self.output_picker = FilePicker(mode="directory")
        output_hint = QLabel(tr('Sem pasta de saída, os arquivos vão para "processados", dentro da pasta de entrada.'))
        output_hint.setWordWrap(True)

        self.operation_combo = QComboBox()
        self.operation_combo.addItems([tr(label) for label, _suffix in _OPERATIONS])

        self.level_combo = QComboBox()
        for level, _name, _badge, _effect, short in _LEVELS:
            self.level_combo.addItem(tr(short), level)
        self.level_combo.setCurrentIndex(1)
        self.language_combo = QComboBox()
        languages = get_available_languages()
        for code in languages:
            self.language_combo.addItem(tr(_LANGUAGE_NAMES.get(code, code)), code)
        for code in ("por", "eng"):
            if code in languages:
                self.language_combo.setCurrentIndex(self.language_combo.findData(code))
                break
        self.watermark_edit = QLineEdit(tr("CONFIDENCIAL"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 1_000_000)
        self.start_spin.setValue(1)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.options_stack = QStackedWidget()
        self._ocr_available = bool(find_tesseract() and languages)
        ocr_label = (
            tr("Idioma do texto:")
            if self._ocr_available
            else tr("Tesseract não encontrado: instale-o para usar o OCR (veja a aba OCR).")
        )
        for label, widget in (
            (tr("Nível de compressão:"), self.level_combo),
            (ocr_label, self.language_combo if self._ocr_available else None),
            (tr("Texto da marca d'água:"), self.watermark_edit),
            (tr("Começar a numeração em:"), self.start_spin),
            (tr("Senha para abrir:"), self.password_edit),
            (tr("Sem opções: cada arquivo vira PDF/A-2b."), None),
        ):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            text = QLabel(label)
            text.setWordWrap(True)  # um aviso longo não pode alargar o painel
            panel_layout.addWidget(text)
            if widget is not None:
                panel_layout.addWidget(widget)
            panel_layout.addStretch()
            self.options_stack.addWidget(panel)
        self.operation_combo.currentIndexChanged.connect(self.options_stack.setCurrentIndex)
        for combo in (self.operation_combo, self.level_combo, self.language_combo):
            # Encolhem com o painel em vez de exigir a largura do texto mais longo.
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)

        self.process_button = QPushButton(tr("Processar"))
        self.action_buttons.append(self.process_button)
        self.process_button.clicked.connect(self._process)
        self.operation_combo.currentIndexChanged.connect(
            lambda index: self.process_button.setEnabled(index != _OCR or self._ocr_available)
        )
        self.results_table = QTableWidget(0, 2)
        self.results_table.setHorizontalHeaderLabels([tr("Arquivo"), tr("Resultado")])
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.verticalHeader().hide()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Pasta com os PDFs:")))
        layout.addWidget(self.input_picker)
        layout.addWidget(self.found_label)
        layout.addWidget(QLabel(tr("Pasta de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(output_hint)
        layout.addWidget(QLabel(tr("Operação:")))
        layout.addWidget(self.operation_combo)
        layout.addWidget(self.options_stack)
        layout.addWidget(self.process_button)
        layout.addWidget(self.results_table, 1)
        layout.addWidget(self.status_label)

    def _update_found(self) -> None:
        folder = self.input_picker.path()
        count = len(pdfs_in_folder(folder)) if folder and os.path.isdir(folder) else 0
        self.found_label.setText(tr("{count} PDF(s) na pasta.").format(count=count))

    def _operation(self):
        """A operação escolhida, com as opções lidas agora (na thread da interface)."""
        index = self.operation_combo.currentIndex()
        if index == _COMPRESS:
            level = self.level_combo.currentData()
            return lambda src, dst, progress: CompressPDF().run(src, dst, level=level, progress=progress)
        if index == _OCR:
            language = self.language_combo.currentData() or "eng"
            return lambda src, dst, progress: OCRDocument().run(src, dst, language=language, progress=progress)
        if index == _WATERMARK:
            text = self.watermark_edit.text()
            return lambda src, dst, _progress: AddWatermark().run(src, dst, text)
        if index == _NUMBERS:
            start = self.start_spin.value()
            return lambda src, dst, _progress: AddPageNumbers().run(src, dst, start_at=start)
        if index == _PROTECT:
            password = self.password_edit.text()
            return lambda src, dst, _progress: ProtectPDF().run(src, dst, password)
        return lambda src, dst, progress: ConvertToPDFA().run(src, dst, progress=progress)

    def _process(self) -> None:
        folder = self.input_picker.path()
        if not folder or not os.path.isdir(folder):
            self.status_label.setText(tr("Escolha a pasta com os PDFs."))
            return
        index = self.operation_combo.currentIndex()
        if index == _WATERMARK and not self.watermark_edit.text().strip():
            self.status_label.setText(tr("Digite o texto da marca d'água."))
            return
        if index == _PROTECT and not self.password_edit.text():
            self.status_label.setText(tr("Digite a senha."))
            return
        paths = pdfs_in_folder(folder)
        if not paths:
            self.status_label.setText(tr("Nenhum PDF na pasta escolhida."))
            return
        output_dir = self.output_picker.path() or os.path.join(folder, "processados")
        operation, suffix = self._operation(), _OPERATIONS[index][1]
        clear_passwords(self)
        self.results_table.setRowCount(0)
        self.status_label.clear()
        run_task(
            self,
            tr("Processar em lote"),
            lambda progress: BatchProcess().run(paths, output_dir, operation, suffix, progress=progress),
            on_success=lambda results: self._show_results(results, output_dir),
        )

    def _show_results(self, results, output_dir: str) -> None:
        rows = []
        for result in results:
            outcome = (
                tr("Salvo como {name}").format(name=os.path.basename(result.output_path))
                if result.error is None
                else tr("Falhou: {error}").format(error=describe_error(result.error)[0])
            )
            rows.append((os.path.basename(result.input_path), outcome))
        self.results_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.results_table.setItem(row, column, QTableWidgetItem(value))
        self.results_table.resizeColumnToContents(0)

        failed = sum(result.error is not None for result in results)
        message = tr("{done} de {total} arquivo(s) processado(s) em {folder}.").format(
            done=len(results) - failed, total=len(results), folder=_breakable(output_dir)
        )
        if failed:
            message += " " + tr("Falharam: {count}.").format(count=failed)
        report_path = os.path.join(output_dir, REPORT_NAME)
        try:
            write_table(report_path, [tr("Arquivo"), tr("Resultado")], rows)
            message += " " + tr("Relatório: {path}").format(path=REPORT_NAME)
        except OSError as exc:
            message += " " + tr("O relatório não foi salvo: {error}").format(error=error_text(exc))
        self.status_label.setText(message)
