"""Aba de numeração de páginas de PDFs."""

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget

from core.page_numbers import AddPageNumbers
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class PageNumbersPage(QWidget):
    """Permite adicionar números de página no rodapé de um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="numerado"
        )

        self.start_at_spin = QSpinBox()
        self.start_at_spin.setRange(0, 9999)
        self.start_at_spin.setValue(1)

        apply_button = QPushButton(tr("Adicionar numeração"))
        apply_button.clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Começar em:")))
        layout.addWidget(self.start_at_spin)
        layout.addWidget(apply_button)

    def _apply(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Numeração de páginas"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Numeração de páginas"), tr("Escolha o arquivo de saída."))
            return

        try:
            AddPageNumbers().run(input_path, output_path, start_at=self.start_at_spin.value())
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("Numeração de páginas"),
                tr("Falha ao numerar páginas: {error}").format(error=exc),
            )
            return

        self.session.open(output_path)
        QMessageBox.information(
            self, tr("Numeração de páginas"), tr("Numeração adicionada com sucesso.")
        )
