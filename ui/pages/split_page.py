"""Aba de divisão de PDFs."""

import os

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base import READ, open_reader
from core.split import SplitAtBlankPages, SplitByBookmarks, SplitByRanges, SplitBySize, SplitPDF
from ui.i18n import tr
from ui.page_ranges import format_page_ranges, parse_page_ranges
from ui.tasks import run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success

_MB = 1024 * 1024


class SplitPage(QWidget):
    """Permite dividir um PDF em múltiplos arquivos: N páginas por vez, por marcador de nível
    superior do sumário, por grupos de páginas digitados (ou as selecionadas nas miniaturas),
    por tamanho máximo de arquivo ou a cada página em branco."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(mode="directory")

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            tr("Por número de páginas"),
            tr("Por marcadores"),
            tr("Por intervalos"),
            tr("Por tamanho máximo"),
            tr("A cada página em branco"),
        ])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_by_count_panel())
        self.stack.addWidget(self._build_by_bookmarks_panel())
        self.stack.addWidget(self._build_by_ranges_panel())
        self.stack.addWidget(self._build_by_size_panel())
        self.stack.addWidget(self._build_at_blank_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Pasta de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _panel(self, button_text: str, action, *rows) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        for row in rows:
            if isinstance(row, QWidget):
                layout.addWidget(row)
            else:
                layout.addLayout(row)
        button = QPushButton(button_text)
        self.action_buttons.append(button)
        button.clicked.connect(action)
        layout.addWidget(button)
        return widget

    @staticmethod
    def _note(text: str) -> QLabel:
        note = QLabel(text)
        note.setWordWrap(True)
        return note

    @staticmethod
    def _row(*widgets) -> QHBoxLayout:
        row = QHBoxLayout()
        for widget in widgets:
            row.addWidget(widget)
        return row

    def _build_by_count_panel(self) -> QWidget:
        self.pages_per_file_spin = QSpinBox()
        self.pages_per_file_spin.setMinimum(1)
        self.pages_per_file_spin.setValue(1)
        return self._panel(
            tr("Dividir"), self._split_by_count, self._row(QLabel(tr("Páginas por arquivo:")), self.pages_per_file_spin)
        )

    def _build_by_bookmarks_panel(self) -> QWidget:
        note = self._note(
            tr(
                "Um arquivo por marcador de nível superior do sumário — cada arquivo vai da "
                "página do marcador até a página anterior ao próximo. Marcadores aninhados "
                "(subtópicos) não geram corte."
            )
        )
        return self._panel(tr("Dividir por marcadores"), self._split_by_bookmarks, note)

    def _build_by_ranges_panel(self) -> QWidget:
        self.ranges_edit = QLineEdit()
        self.ranges_edit.setPlaceholderText(tr("ex.: 1-3; 4-10; 11-"))
        self.selection_button = QPushButton(tr("Usar seleção"))
        self.selection_button.setToolTip(tr("As páginas selecionadas nas miniaturas, num arquivo só (Ctrl ou Shift + clique)."))
        self.selection_button.clicked.connect(
            lambda: self.ranges_edit.setText(format_page_ranges(self.session.selected_pages()))
        )
        note = self._note(
            tr("Um arquivo por grupo, separados por ponto e vírgula; dentro de um grupo, vírgulas "
               "juntam páginas soltas (1-3, 5; 6-10). Um grupo só extrai aquelas páginas.")
        )
        return self._panel(tr("Dividir por intervalos"), self._split_by_ranges, note, self._row(self.ranges_edit, self.selection_button))

    def _build_by_size_panel(self) -> QWidget:
        self.max_size_spin = QDoubleSpinBox()
        self.max_size_spin.setRange(0.1, 10_000)
        self.max_size_spin.setDecimals(1)
        self.max_size_spin.setValue(10)
        self.max_size_spin.setSuffix(" MB")
        note = self._note(
            tr("Partes de até esse tamanho, com as páginas na ordem (para anexar em e-mail ou "
               "enviar a um sistema com limite). Uma página que sozinha passa do limite fica num "
               "arquivo próprio.")
        )
        return self._panel(
            tr("Dividir por tamanho"), self._split_by_size, note, self._row(QLabel(tr("Tamanho máximo:")), self.max_size_spin)
        )

    def _build_at_blank_panel(self) -> QWidget:
        note = self._note(
            tr("Para lotes escaneados com uma folha em branco entre os documentos: cada página em "
               "branco separa um arquivo do próximo e não vai para nenhum.")
        )
        return self._panel(tr("Dividir nas páginas em branco"), self._split_at_blank, note)

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _start(self, make_task, describe=None) -> None:
        """Confere entrada e pasta e roda `make_task(input_path, output_dir)` (que recebe o
        andamento); `describe(paths)` acrescenta algo à mensagem final."""
        input_path = self.session.path()
        output_dir = self.output_picker.path()
        if not input_path:
            notify_error(self, tr("Dividir"), tr("Abra um PDF para começar."))
            return
        if not output_dir:
            notify_error(self, tr("Dividir"), tr("Escolha a pasta de saída."))
            return

        def done(output_paths):
            message = tr("PDF dividido em {count} arquivo(s).").format(count=len(output_paths))
            extra = describe(output_paths) if describe else ""
            notify_success(self, tr("Dividir"), f"{message}\n\n{extra}" if extra else message)

        run_task(
            self,
            tr("Dividir"),
            make_task(input_path, output_dir),
            on_success=done,
            error_message=tr("Falha ao dividir: {error}"),
        )

    def _split_by_count(self):
        pages_per_file = self.pages_per_file_spin.value()
        self._start(lambda path, folder: lambda _progress: SplitPDF().run(path, folder, pages_per_file=pages_per_file))

    def _split_by_bookmarks(self):
        self._start(lambda path, folder: lambda _progress: SplitByBookmarks().run(path, folder))

    def _split_by_ranges(self):
        text = self.ranges_edit.text()
        if not text.strip(";, "):
            notify_error(self, tr("Dividir"), tr("Informe as páginas de cada arquivo."))
            return

        def task(path, folder):
            def run(_progress):
                total = len(open_reader(path, purpose=READ).pages)
                groups = [parse_page_ranges(group, total) for group in text.split(";") if group.strip(", ")]
                return SplitByRanges().run(path, folder, groups)

            return run

        self._start(task)

    def _split_by_size(self):
        max_bytes = round(self.max_size_spin.value() * _MB)

        def oversized(paths):
            big = [os.path.basename(p) for p in paths if os.path.getsize(p) > max_bytes]
            if not big:
                return ""
            return tr("Passaram do limite, por terem uma página maior que ele: {files}.").format(files=", ".join(big))

        self._start(lambda path, folder: lambda progress: SplitBySize().run(path, folder, max_bytes, progress), oversized)

    def _split_at_blank(self):
        self._start(lambda path, folder: lambda progress: SplitAtBlankPages().run(path, folder, progress))
