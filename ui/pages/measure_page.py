"""Aba de medição: distância entre dois pontos, arrastando no visualizador central."""

from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.i18n import tr
from ui.measure_state import UNITS, format_distance
from ui.widgets.document_source_bar import DocumentSourceBar

_UNIT_LABELS = {"mm": "Milímetros (mm)", "cm": "Centímetros (cm)", "in": "Polegadas (in)", "pt": "Pontos PDF (pt)"}


class MeasurePage(QWidget):
    """Permite medir a distância entre dois pontos de um PDF: arraste no visualizador
    central entre os dois pontos desejados. Assume o `/UserUnit` padrão (1 ponto = 1/72
    polegada) — PDFs de engenharia com uma escala declarada diferente não são detectados."""

    def __init__(self, session, measure_state, parent=None):
        super().__init__(parent)
        self.session = session
        self.measure_state = measure_state

        self.source_bar = DocumentSourceBar(session)

        instructions = QLabel(
            tr("Arraste no visualizador entre dois pontos para medir a distância entre eles.")
        )
        instructions.setWordWrap(True)

        self.unit_combo = QComboBox()
        for unit in UNITS:
            self.unit_combo.addItem(tr(_UNIT_LABELS[unit]))
        self.unit_combo.setCurrentIndex(UNITS.index(measure_state.unit()))
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)

        self.result_label = QLabel()
        self.result_label.setObjectName("pageSubtitle")
        measure_state.result_changed.connect(self._update_result_label)
        measure_state.unit_changed.connect(self._update_result_label)
        self._update_result_label()

        clear_button = QPushButton(tr("Limpar medição"))
        clear_button.clicked.connect(measure_state.clear_result)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(instructions)
        layout.addWidget(QLabel(tr("Unidade:")))
        layout.addWidget(self.unit_combo)
        layout.addWidget(self.result_label)
        layout.addWidget(clear_button)

    def _on_unit_changed(self, index: int):
        self.measure_state.set_unit(UNITS[index])

    def _update_result_label(self):
        distance_pt = self.measure_state.last_distance_pt()
        if distance_pt is None:
            self.result_label.setText(tr("Nenhuma medição feita ainda."))
            return
        self.result_label.setText(
            tr("Última medição: {distance}").format(
                distance=format_distance(distance_pt, self.measure_state.unit())
            )
        )
