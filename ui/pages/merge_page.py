"""Aba de mesclagem de PDFs."""

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget

from core.base import READ, open_reader
from core.merge import MergePDF
from ui.i18n import tr
from ui.page_ranges import parse_page_ranges
from ui.tasks import run_task
from ui.widgets.file_list_editor import FileListEditor
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success


class MergePage(QWidget):
    """Permite escolher vários PDFs (e as páginas de cada um), reordená-los e mesclá-los em um
    único arquivo, com um marcador por arquivo ou intercalando frentes e versos."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.file_list_editor = FileListEditor(
            dialog_caption=tr("Selecionar PDFs"), file_filter="PDF (*.pdf)", with_pages=True
        )
        self.output_picker = FilePicker(
            mode="save",
            suggested_source=lambda: (self.file_list_editor.paths() or [None])[0],
            suggested_suffix="mesclado",
        )
        self.bookmark_check = QCheckBox(tr("Um marcador por arquivo (com os marcadores dele dentro)"))
        self.interleave_check = QCheckBox(tr("Intercalar frentes e versos escaneados à parte"))
        self.interleave_check.setToolTip(
            tr("Junta dois arquivos página a página: a 1ª do primeiro, a 1ª do segundo, a 2ª do primeiro...")
        )
        self.reverse_check = QCheckBox(tr("Versos em ordem inversa (o maço virado no scanner)"))
        self.reverse_check.setEnabled(False)
        self.interleave_check.toggled.connect(self.reverse_check.setEnabled)

        merge_button = QPushButton(tr("Mesclar"))
        self.action_buttons.append(merge_button)
        merge_button.clicked.connect(self._merge)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivos a mesclar (na ordem desejada):")))
        layout.addWidget(self.file_list_editor)
        layout.addWidget(self.bookmark_check)
        layout.addWidget(self.interleave_check)
        layout.addWidget(self.reverse_check)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(merge_button)

    def _merge(self):
        entries = self.file_list_editor.entries()
        output_path = self.output_picker.path()

        if not entries:
            notify_error(self, tr("Mesclar"), tr("Adicione pelo menos um arquivo."))
            return
        if self.interleave_check.isChecked() and len(entries) != 2:
            notify_error(self, tr("Mesclar"), tr("Para intercalar, deixe na lista só dois arquivos: o das frentes e o dos versos."))
            return
        if not output_path:
            notify_error(self, tr("Mesclar"), tr("Escolha o arquivo de saída."))
            return

        options = {
            "bookmark_per_file": self.bookmark_check.isChecked(),
            "interleave": self.interleave_check.isChecked(),
            "reverse_second": self.interleave_check.isChecked() and self.reverse_check.isChecked(),
        }

        def task(progress):
            # Na thread de trabalho: saber "8-" exige abrir cada arquivo.
            pages = []
            for path, text in entries:
                if not text:
                    pages.append(None)
                    continue
                try:
                    pages.append(parse_page_ranges(text, len(open_reader(path, purpose=READ).pages)))
                except ValueError as exc:
                    raise ValueError(f"{Path(path).name}: {exc}") from exc
            MergePDF().run([path for path, _text in entries], output_path, progress, pages=pages, **options)

        def done(_result):
            self.session.open(output_path)
            notify_success(self, tr("Mesclar"), tr("PDFs mesclados com sucesso."))

        run_task(
            self,
            tr("Mesclar"),
            task,
            on_success=done,
            error_message=tr("Falha ao mesclar: {error}"),
        )
