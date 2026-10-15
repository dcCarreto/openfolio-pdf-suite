"""Aba de camadas (Optional Content Groups): listar e alternar visibilidade padrão."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.layers import ListLayers, SetLayerVisibility
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class LayersPage(QWidget):
    """Permite listar as camadas (OCGs) de um PDF e alternar a visibilidade padrão de
    cada uma — a mesma preferência que o painel de Camadas do Acrobat grava ao salvar."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        list_button = QPushButton(tr("Listar camadas"))
        list_button.clicked.connect(self._list_layers)
        self.layers_list = QListWidget()

        self.layer_index_spin = QSpinBox()
        self.layer_index_spin.setRange(1, 9999)
        self.visibility_combo = QComboBox()
        self.visibility_combo.addItems([tr("Visível"), tr("Oculta")])

        self.output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="camadas"
        )
        apply_button = QPushButton(tr("Aplicar visibilidade"))
        apply_button.clicked.connect(self._apply_visibility)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(list_button)
        layout.addWidget(self.layers_list)
        layout.addWidget(QLabel(tr("Número da camada:")))
        layout.addWidget(self.layer_index_spin)
        layout.addWidget(QLabel(tr("Nova visibilidade:")))
        layout.addWidget(self.visibility_combo)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(apply_button)

    def _list_layers(self):
        input_path = self.session.path()
        self.layers_list.clear()
        if not input_path:
            QMessageBox.warning(self, tr("Camadas"), tr("Abra um PDF para começar."))
            return

        try:
            layers = ListLayers().run(input_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Camadas"), tr("Falha ao listar camadas: {error}").format(error=exc)
            )
            return

        if not layers:
            self.layers_list.addItem(tr("Este PDF não tem camadas (Optional Content Groups)."))
            return
        for layer in layers:
            status = tr("visível") if layer.visible else tr("oculta")
            self.layers_list.addItem(f"#{layer.index + 1} — {layer.name} — {status}")

    def _apply_visibility(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Camadas"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Camadas"), tr("Escolha o arquivo de saída."))
            return

        visible = self.visibility_combo.currentIndex() == 0

        try:
            SetLayerVisibility().run(
                input_path, output_path, layer_index=self.layer_index_spin.value() - 1, visible=visible
            )
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Camadas"), tr("Falha ao alterar visibilidade: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Camadas"), tr("Visibilidade da camada alterada com sucesso."))
