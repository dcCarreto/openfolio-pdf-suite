"""Aba de compressão de PDFs."""

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QPushButton, QVBoxLayout, QWidget

from core.compress import CompressPDF
from ui.i18n import plural, tr
from ui.tasks import call_with_progress, run_task
from ui.widgets.choice_cards import ChoiceCards
from ui.widgets.document_source_bar import DocumentSourceBar, format_size
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_info, notify_success

# (nível, nome, selo, efeito no arquivo, rótulo curto). Os DPI são os de core/compress.py; sem
# como estimar o tamanho antes de comprimir, os cartões não mostram estimativa.
_LEVELS = [
    ("light", "Leve", "", "Quase sem diferença visível. As imagens não perdem qualidade.", "Leve · sem perda"),
    ("medium", "Equilibrada", "recomendada", "Boa para enviar por e-mail. Fotos a 150 DPI.", "Equilibrada · boa para e-mail"),
    ("strong", "Forte", "", "Menor arquivo; fotos podem perder nitidez. 100 DPI.", "Forte · menor arquivo"),
]


class CompressPage(QWidget):
    """Permite reduzir o tamanho de um arquivo PDF."""

    options_title = "Quanto comprimir"

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.source_bar = DocumentSourceBar(session, empty_hint="Abra ou arraste o PDF que quer diminuir.")
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="comprimido"
        )

        self.level_cards = ChoiceCards(_LEVELS)
        self.level_combo = self.level_cards.combo
        self.level_combo.setCurrentIndex(1)

        self.grayscale_check = QCheckBox(tr("Tons de cinza · menor, mas perde a cor"))

        compress_button = QPushButton(tr("Comprimir PDF"))
        self.action_buttons.append(compress_button)
        compress_button.clicked.connect(self._compress)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.source_bar)
        layout.addWidget(self.output_picker)
        layout.addWidget(self.level_cards)
        layout.addWidget(self.grayscale_check)
        layout.addWidget(compress_button)

    def _compress(self):
        input_path = self.session.path()
        applies = self.output_picker.applies_to_document()
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
            sizes = {"original": format_size(result.original_size), "compressed": format_size(result.compressed_size)}
            if not result.written:
                notify_info(
                    self,
                    tr("Comprimir"),
                    tr("O arquivo não ficaria menor ({original} → {compressed}).").format(**sizes)
                    + "\n"
                    + tr("Nada foi gravado. Tente um nível mais forte."),
                )
                return
            self.session.open(output_path)
            details = tr("{reduction}% menor.").format(reduction=f"{result.reduction_percent:.0f}")
            if result.images_recompressed:
                details += " " + plural(result.images_recompressed, "1 imagem recomprimida.", "{count} imagens recomprimidas.")
            if applies:
                details += " " + tr("Aplicado neste documento; salve para gravar no arquivo.")
            else:
                details += " " + tr("Gravado em {name}.").format(name=Path(output_path).name)
            notify_success(self, tr("Comprimir"), tr("Pronto: {original} → {compressed}").format(**sizes) + "\n" + details)

        run_task(
            self,
            tr("Comprimir"),
            task,
            on_success=done,
            error_message=tr("Não foi possível comprimir.") + "\n{error}",
        )
