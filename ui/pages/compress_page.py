"""Aba de compressão de PDFs."""

from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget

from core.compress import CompressPDF
from ui.i18n import tr
from ui.tasks import call_with_progress, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_info, notify_success

_LEVELS = [
    ("light", "Leve (sem perda de qualidade)"),
    ("medium", "Média (imagens a 150 DPI)"),
    ("strong", "Forte (imagens a 100 DPI)"),
]


class CompressPage(QWidget):
    """Permite reduzir o tamanho de um arquivo PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="comprimido"
        )

        self.level_combo = QComboBox()
        for level, label in _LEVELS:
            self.level_combo.addItem(tr(label), level)
        self.level_combo.setCurrentIndex(1)

        self.grayscale_check = QCheckBox(tr("Converter as imagens para escala de cinza"))

        compress_button = QPushButton(tr("Comprimir"))
        self.action_buttons.append(compress_button)
        compress_button.clicked.connect(self._compress)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Nível de compressão:")))
        layout.addWidget(self.level_combo)
        layout.addWidget(self.grayscale_check)
        layout.addWidget(compress_button)

    def _compress(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            notify_error(self, tr("Comprimir"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Comprimir"), tr("Escolha o arquivo de saída."))
            return

        task = call_with_progress(
            CompressPDF().run,
            input_path,
            output_path,
            level=self.level_combo.currentData(),
            grayscale=self.grayscale_check.isChecked(),
        )

        def done(result):
            sizes = {
                "original": f"{result.original_size / 1024:.1f}",
                "compressed": f"{result.compressed_size / 1024:.1f}",
            }
            if not result.written:
                notify_info(
                    self,
                    tr("Comprimir"),
                    tr(
                        "O arquivo não ficou menor ({original} KB -> {compressed} KB), então nada "
                        "foi gravado. Tente um nível mais forte."
                    ).format(**sizes),
                )
                return
            self.session.open(output_path)
            message = tr("PDF comprimido: {original} KB -> {compressed} KB ({reduction}% menor).").format(
                reduction=f"{result.reduction_percent:.0f}", **sizes
            )
            if result.images_recompressed:
                message += "\n" + tr("{count} imagem(ns) recomprimida(s).").format(count=result.images_recompressed)
            notify_success(self, tr("Comprimir"), message)

        run_task(
            self,
            tr("Comprimir"),
            task,
            on_success=done,
            error_message=tr("Falha ao comprimir: {error}"),
        )
