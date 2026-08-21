"""Aba de divisão de PDFs."""

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.split import SplitByBookmarks, SplitPDF
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class SplitPage(QWidget):
    """Permite dividir um PDF em múltiplos arquivos, N páginas por vez ou por marcador de
    nível superior do sumário."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(mode="directory")

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Por número de páginas"), tr("Por marcadores")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_by_count_panel())
        self.stack.addWidget(self._build_by_bookmarks_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Pasta de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_by_count_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pages_per_file_spin = QSpinBox()
        self.pages_per_file_spin.setMinimum(1)
        self.pages_per_file_spin.setValue(1)

        split_button = QPushButton(tr("Dividir"))
        split_button.clicked.connect(self._split_by_count)

        pages_layout = QHBoxLayout()
        pages_layout.addWidget(QLabel(tr("Páginas por arquivo:")))
        pages_layout.addWidget(self.pages_per_file_spin)

        layout.addLayout(pages_layout)
        layout.addWidget(split_button)
        return widget

    def _build_by_bookmarks_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Um arquivo por marcador de nível superior do sumário — cada arquivo vai da "
                "página do marcador até a página anterior ao próximo. Marcadores aninhados "
                "(subtópicos) não geram corte."
            )
        )
        note.setWordWrap(True)

        split_button = QPushButton(tr("Dividir por marcadores"))
        split_button.clicked.connect(self._split_by_bookmarks)

        layout.addWidget(note)
        layout.addWidget(split_button)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _split_by_count(self):
        input_path = self.session.path()
        output_dir = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Dividir"), tr("Abra um PDF para começar."))
            return
        if not output_dir:
            QMessageBox.warning(self, tr("Dividir"), tr("Escolha a pasta de saída."))
            return

        try:
            output_paths = SplitPDF().run(
                input_path, output_dir, pages_per_file=self.pages_per_file_spin.value()
            )
        except Exception as exc:
            QMessageBox.critical(self, tr("Dividir"), tr("Falha ao dividir: {error}").format(error=exc))
            return

        QMessageBox.information(
            self,
            tr("Dividir"),
            tr("PDF dividido em {count} arquivo(s).").format(count=len(output_paths)),
        )

    def _split_by_bookmarks(self):
        input_path = self.session.path()
        output_dir = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Dividir"), tr("Abra um PDF para começar."))
            return
        if not output_dir:
            QMessageBox.warning(self, tr("Dividir"), tr("Escolha a pasta de saída."))
            return

        try:
            output_paths = SplitByBookmarks().run(input_path, output_dir)
        except Exception as exc:
            QMessageBox.critical(self, tr("Dividir"), tr("Falha ao dividir: {error}").format(error=exc))
            return

        QMessageBox.information(
            self,
            tr("Dividir"),
            tr("PDF dividido em {count} arquivo(s).").format(count=len(output_paths)),
        )
