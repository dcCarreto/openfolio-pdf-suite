"""Aba de anotações e marcação: realce, sublinhado, riscado, notas, caneta e carimbo."""

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.annotations import AddAnnotations
from ui.annotation_state import AnnotationState, DEFAULT_COLOR
from ui.document_session import DocumentSession
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_TOOLS = [
    ("select", "Selecionar/Apagar"),
    ("highlight", "Realce"),
    ("underline", "Sublinhado"),
    ("strikeout", "Riscado"),
    ("note", "Nota adesiva"),
    ("ink", "Caneta"),
    ("stamp", "Carimbo"),
]

_COLORS = [
    ("ffeb3b", "Amarelo"),
    ("f44336", "Vermelho"),
    ("4caf50", "Verde"),
    ("2196f3", "Azul"),
    ("000000", "Preto"),
]

_STAMP_TEXTS = ["APROVADO", "CONFIDENCIAL", "RASCUNHO", "REVISADO", "URGENTE"]


class AnnotationsPage(QWidget):
    """Permite marcar o PDF aberto (realce, sublinhado, riscado, notas, caneta, carimbo)
    diretamente sobre o visualizador central, e gravar o resultado em um novo arquivo."""

    def __init__(self, session: DocumentSession, annotation_state: AnnotationState, parent=None):
        super().__init__(parent)
        self.session = session
        self.annotation_state = annotation_state

        self.source_bar = DocumentSourceBar(session)

        self.tool_buttons: dict[str, QPushButton] = {}
        tools_layout = QVBoxLayout()
        tool_group = QButtonGroup(self)
        tool_group.setExclusive(True)
        self._tool_group = tool_group
        for key, label in _TOOLS:
            button = QPushButton(tr(label))
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, k=key: self.annotation_state.set_tool(k))
            tool_group.addButton(button)
            tools_layout.addWidget(button)
            self.tool_buttons[key] = button

        current_tool = annotation_state.active_tool() or "select"
        annotation_state.set_tool(current_tool)
        self.tool_buttons[current_tool].setChecked(True)

        self.color_buttons: dict[str, QPushButton] = {}
        colors_layout = QHBoxLayout()
        color_group = QButtonGroup(self)
        color_group.setExclusive(True)
        self._color_group = color_group
        for color, name in _COLORS:
            button = QPushButton()
            button.setObjectName("colorSwatch")
            button.setCheckable(True)
            button.setFixedSize(26, 26)
            button.setToolTip(tr(name))
            button.setStyleSheet(
                f"QPushButton {{ background-color: #{color}; border: 2px solid transparent; "
                "border-radius: 4px; }"
                "QPushButton:checked { border: 2px solid #ffffff; }"
            )
            button.clicked.connect(lambda _checked, c=color: self.annotation_state.set_color(c))
            color_group.addButton(button)
            colors_layout.addWidget(button)
            self.color_buttons[color] = button
        colors_layout.addStretch()
        self.color_buttons.get(annotation_state.active_color(), self.color_buttons[DEFAULT_COLOR]).setChecked(True)

        self.stamp_label = QLabel(tr("Texto do carimbo:"))
        self.stamp_combo = QComboBox()
        self.stamp_combo.addItems([tr(text) for text in _STAMP_TEXTS])
        self.stamp_combo.currentIndexChanged.connect(self._on_stamp_text_changed)
        self._on_stamp_text_changed(0)
        annotation_state.tool_changed.connect(self._update_stamp_visibility)
        self._update_stamp_visibility()

        self.pending_label = QLabel()
        clear_button = QPushButton(tr("Limpar pendentes"))
        clear_button.clicked.connect(self.annotation_state.clear_pending)
        annotation_state.pending_changed.connect(self._update_pending_label)
        self._update_pending_label()

        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="anotado"
        )
        save_button = QPushButton(tr("Salvar anotações"))
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Ferramenta:")))
        layout.addLayout(tools_layout)
        layout.addWidget(QLabel(tr("Cor:")))
        layout.addLayout(colors_layout)
        layout.addWidget(self.stamp_label)
        layout.addWidget(self.stamp_combo)
        layout.addWidget(self.pending_label)
        layout.addWidget(clear_button)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(save_button)

    def _on_stamp_text_changed(self, index: int):
        self.annotation_state.set_stamp_text(tr(_STAMP_TEXTS[index]))

    def _update_stamp_visibility(self):
        is_stamp = self.annotation_state.active_tool() == "stamp"
        self.stamp_label.setVisible(is_stamp)
        self.stamp_combo.setVisible(is_stamp)

    def _update_pending_label(self):
        count = len(self.annotation_state.pending())
        self.pending_label.setText(tr("{count} anotação(ões) pendente(s)").format(count=count))

    def _save(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()
        pending = self.annotation_state.pending()

        if not input_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Escolha o arquivo de saída."))
            return
        if not pending:
            QMessageBox.warning(
                self, tr("Anotações"), tr("Adicione pelo menos uma anotação antes de salvar.")
            )
            return

        try:
            AddAnnotations().run(input_path, output_path, pending)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anotações"), tr("Falha ao salvar anotações: {error}").format(error=exc)
            )
            return

        self.annotation_state.clear_pending()
        self.session.open(output_path)
        QMessageBox.information(self, tr("Anotações"), tr("Anotações salvas com sucesso."))
