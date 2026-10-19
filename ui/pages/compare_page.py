"""Aba de comparação: diff de texto, diff visual e comparação lado a lado entre duas versões
de um PDF."""

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.compare import CompareDocuments, CompareText, CompareVisual
from ui.i18n import tr
from ui.tasks import call_with_progress, run_task
from ui.viewer.compare_view import CompareWindow
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class ComparePage(QWidget):
    """Permite comparar duas versões de um PDF: lado a lado, com as diferenças de texto
    destacadas; diff de texto por página; ou diff visual (imagem por página destacando as
    áreas que mudaram)."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.compare_window: CompareWindow | None = None

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Comparar lado a lado"), tr("Comparar texto"), tr("Comparar visualmente")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_side_by_side_panel())
        self.stack.addWidget(self._build_text_panel())
        self.stack.addWidget(self._build_visual_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_side_by_side_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(
            tr(
                "Mostra as duas versões lado a lado, com as diferenças de texto destacadas e a "
                "rolagem sincronizada. O texto comparado é o do documento inteiro: o que só "
                "passou para outra página não conta como diferença."
            )
        )
        hint.setWordWrap(True)
        self.side_b_picker = FilePicker(mode="open", file_filter="PDF (*.pdf)")
        compare_button = QPushButton(tr("Comparar lado a lado"))
        compare_button.clicked.connect(self._compare_side_by_side)

        layout.addWidget(hint)
        layout.addWidget(QLabel(tr("A: documento aberto")))
        layout.addWidget(DocumentSourceBar(self.session))
        layout.addWidget(QLabel(tr("B: comparar com")))
        layout.addWidget(self.side_b_picker)
        layout.addWidget(compare_button)
        layout.addStretch()
        return widget

    def _build_text_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_a_picker = FilePicker(mode="open", file_filter="PDF (*.pdf)")
        self.text_b_picker = FilePicker(mode="open", file_filter="PDF (*.pdf)")
        compare_button = QPushButton(tr("Comparar"))
        compare_button.clicked.connect(self._compare_text)
        self.text_results_list = QListWidget()

        layout.addWidget(QLabel(tr("PDF A:")))
        layout.addWidget(self.text_a_picker)
        layout.addWidget(QLabel(tr("PDF B:")))
        layout.addWidget(self.text_b_picker)
        layout.addWidget(compare_button)
        layout.addWidget(self.text_results_list)
        return widget

    def _build_visual_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.visual_a_picker = FilePicker(mode="open", file_filter="PDF (*.pdf)")
        self.visual_b_picker = FilePicker(mode="open", file_filter="PDF (*.pdf)")
        self.visual_output_picker = FilePicker(mode="directory")
        compare_button = QPushButton(tr("Comparar"))
        compare_button.clicked.connect(self._compare_visual)
        self.visual_results_list = QListWidget()

        layout.addWidget(QLabel(tr("PDF A:")))
        layout.addWidget(self.visual_a_picker)
        layout.addWidget(QLabel(tr("PDF B:")))
        layout.addWidget(self.visual_b_picker)
        layout.addWidget(QLabel(tr("Pasta de saída (imagens de diferença):")))
        layout.addWidget(self.visual_output_picker)
        layout.addWidget(compare_button)
        layout.addWidget(self.visual_results_list)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _compare_side_by_side(self):
        path_a = self.session.path()
        path_b = self.side_b_picker.path()
        if not path_a or not path_b:
            QMessageBox.warning(self, tr("Comparar"), tr("Abra o documento A e escolha o PDF B a comparar."))
            return

        source = self.session.source_path() or path_a
        title_a = Path(source).name + (" *" if self.session.is_modified() else "")

        def done(diff):
            if self.compare_window is not None:
                self.compare_window.close()
            window = CompareWindow(title_a, path_a, Path(path_b).name, path_b, diff, parent=self)
            # A janela anterior só é destruída depois: não pode esquecer a nova.
            window.destroyed.connect(lambda: self._forget_compare_window(window))
            self.compare_window = window
            window.show()

        run_task(
            self,
            tr("Comparar"),
            call_with_progress(CompareDocuments().run, path_a, path_b),
            on_success=done,
            error_message=tr("Falha ao comparar: {error}"),
        )

    def _forget_compare_window(self, window):
        if self.compare_window is window:
            self.compare_window = None

    def _compare_text(self):
        path_a = self.text_a_picker.path()
        path_b = self.text_b_picker.path()
        self.text_results_list.clear()

        if not path_a or not path_b:
            QMessageBox.warning(self, tr("Comparar"), tr("Escolha os dois arquivos PDF a comparar."))
            return

        task = call_with_progress(CompareText().run, path_a, path_b)

        def done(results):
            for result in results:
                if not result.changed:
                    self.text_results_list.addItem(
                        tr("Página {page}: sem alterações").format(page=result.page_index + 1)
                    )
                    continue
                preview = " | ".join(result.diff_lines[:4])
                self.text_results_list.addItem(
                    tr("Página {page}: {count} linha(s) diferentes — {preview}").format(
                        page=result.page_index + 1, count=len(result.diff_lines), preview=preview
                    )
                )

        run_task(
            self,
            tr("Comparar"),
            task,
            on_success=done,
            error_message=tr("Falha ao comparar: {error}"),
        )

    def _compare_visual(self):
        path_a = self.visual_a_picker.path()
        path_b = self.visual_b_picker.path()
        output_dir = self.visual_output_picker.path()
        self.visual_results_list.clear()

        if not path_a or not path_b:
            QMessageBox.warning(self, tr("Comparar"), tr("Escolha os dois arquivos PDF a comparar."))
            return
        if not output_dir:
            QMessageBox.warning(self, tr("Comparar"), tr("Escolha a pasta de saída."))
            return

        task = call_with_progress(CompareVisual().run, path_a, path_b, output_dir)

        def done(results):
            status_labels = {
                "compared": tr("comparada"),
                "only_in_a": tr("só existe em A"),
                "only_in_b": tr("só existe em B"),
                "size_mismatch": tr("tamanhos diferentes, não comparada"),
            }
            for result in results:
                label = status_labels[result.status]
                if result.status == "compared":
                    self.visual_results_list.addItem(
                        tr("Página {page}: {label} — {percent:.1f}% diferente").format(
                            page=result.page_index + 1, label=label, percent=result.changed_fraction * 100
                        )
                    )
                else:
                    self.visual_results_list.addItem(
                        tr("Página {page}: {label}").format(page=result.page_index + 1, label=label)
                    )

        run_task(
            self,
            tr("Comparar"),
            task,
            on_success=done,
            error_message=tr("Falha ao comparar: {error}"),
        )
