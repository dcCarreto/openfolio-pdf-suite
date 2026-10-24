"""Aba Limpar escaneados (A08): remove páginas em branco, endireita páginas tortas e corta
as margens brancas do documento aberto, numa versão nova (Ctrl+Z desfaz)."""

from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget

from core.scan_cleanup import CleanScannedPages
from ui.i18n import tr
from ui.page_ranges import format_page_ranges
from ui.tasks import run_task


class ScanCleanupPage(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.blank_check = QCheckBox(tr("Remover páginas em branco"))
        self.deskew_check = QCheckBox(tr("Endireitar páginas tortas (até 5°)"))
        self.crop_check = QCheckBox(tr("Cortar as margens brancas"))
        for check in (self.blank_check, self.deskew_check, self.crop_check):
            check.setChecked(True)
        self.clean_button = QPushButton(tr("Limpar páginas"))
        self.action_buttons.append(self.clean_button)
        self.clean_button.clicked.connect(self._clean)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        note = QLabel(
            tr(
                "Feito para páginas escaneadas: a análise olha a imagem da página, não o texto. "
                "Confira o resultado; Ctrl+Z desfaz."
            )
        )
        note.setWordWrap(True)
        note.setObjectName("pageSubtitle")

        layout = QVBoxLayout(self)
        layout.addWidget(self.blank_check)
        layout.addWidget(self.deskew_check)
        layout.addWidget(self.crop_check)
        layout.addWidget(self.clean_button)
        layout.addWidget(self.status_label)
        layout.addWidget(note)
        layout.addStretch()

    def _clean(self) -> None:
        input_path = self.session.path()
        if not input_path:
            self.status_label.setText(tr("Abra um PDF para começar."))
            return
        options = dict(
            remove_blank=self.blank_check.isChecked(),
            deskew=self.deskew_check.isChecked(),
            crop_margins=self.crop_check.isChecked(),
        )
        if not any(options.values()):
            self.status_label.setText(tr("Escolha pelo menos uma limpeza."))
            return
        output_path = self.session.new_version_path()
        self.status_label.clear()
        run_task(
            self,
            tr("Limpar escaneados"),
            lambda progress: CleanScannedPages().run(input_path, output_path, progress=progress, **options),
            on_success=lambda result: self._done(result, output_path),
        )

    def _done(self, result, output_path: str) -> None:
        lines = [
            tr(label).format(pages=format_page_ranges(pages))
            for label, pages in (
                ("Páginas em branco removidas: {pages}.", result.removed),
                ("Páginas endireitadas: {pages}.", result.straightened),
                ("Margens cortadas nas páginas: {pages}.", result.cropped),
            )
            if pages
        ]
        if not lines:
            self.status_label.setText(tr("Nenhuma página precisou de limpeza."))
            return
        if result.removed:
            lines.append(tr("Os números são os das páginas antes da limpeza."))
        self.session.open(output_path)
        self.status_label.setText("\n".join(lines))
