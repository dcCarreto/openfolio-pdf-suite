"""Aba de extração de texto de PDFs."""

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.extract_text import ExtractText
from ui.i18n import tr
from ui.tasks import call, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success


class ExtractTextPage(QWidget):
    """Permite extrair todo o texto de um PDF para um arquivo .txt."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(mode="save", file_filter="Texto (*.txt)")

        extract_button = QPushButton(tr("Extrair texto"))
        self.action_buttons.append(extract_button)
        extract_button.clicked.connect(self._extract)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída (.txt):")))
        layout.addWidget(self.output_picker)
        layout.addWidget(extract_button)

    def _extract(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            notify_error(self, tr("Extrair texto"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Extrair texto"), tr("Escolha o arquivo de saída."))
            return

        task = call(ExtractText().run, input_path, output_path)

        def done(_result):
            notify_success(self, tr("Extrair texto"), tr("Texto extraído com sucesso."))

        run_task(
            self,
            tr("Extrair texto"),
            task,
            on_success=done,
            error_message=tr("Falha ao extrair texto: {error}"),
        )
