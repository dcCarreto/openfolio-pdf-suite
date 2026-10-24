"""Aba de corte e redimensionamento de páginas de PDFs."""

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base import READ, open_reader
from core.crop import CropPages, ScalePages
from core.geometry import PageGeometry
from ui.area_pick_state import AreaPickState
from ui.i18n import tr
from ui.tasks import call, run_task
from ui.page_sizes import CUSTOM_SIZE_LABEL, PAGE_SIZES
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success

_SIZE_LABELS = [*PAGE_SIZES.keys(), CUSTOM_SIZE_LABEL]


class CropPage(QWidget):
    """Permite cortar margens ou redimensionar as páginas de um PDF."""

    def __init__(self, session, area_pick_state: AreaPickState | None = None, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.area_pick_state = area_pick_state or AreaPickState()
        self.area_pick_state.area_picked.connect(self._on_area_picked)
        self._crop_page = 0

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Cortar margens"), tr("Redimensionar")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_crop_panel())
        self.stack.addWidget(self._build_scale_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Operação:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)
        self._on_mode_changed(self.mode_combo.currentIndex())

    def _build_crop_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.crop_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="cortado"
        )

        self.left_spin = self._margin_spin()
        self.bottom_spin = self._margin_spin()
        self.right_spin = self._margin_spin()
        self.top_spin = self._margin_spin()

        for spin in (self.left_spin, self.bottom_spin, self.right_spin, self.top_spin):
            spin.valueChanged.connect(self._publish_area)
        crop_hint = QLabel(tr("Arraste no visualizador a área que deve ficar; as margens são calculadas a partir dela."))
        crop_hint.setWordWrap(True)

        margins_layout = QFormLayout()
        margins_layout.addRow(tr("Esquerda:"), self.left_spin)
        margins_layout.addRow(tr("Baixo:"), self.bottom_spin)
        margins_layout.addRow(tr("Direita:"), self.right_spin)
        margins_layout.addRow(tr("Topo:"), self.top_spin)

        apply_button = QPushButton(tr("Cortar"))
        self.action_buttons.append(apply_button)
        apply_button.clicked.connect(self._crop)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.crop_output_picker)
        layout.addWidget(crop_hint)
        layout.addWidget(QLabel(tr("Margens a cortar (pontos):")))
        layout.addLayout(margins_layout)
        layout.addWidget(apply_button)
        return widget

    def _build_scale_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scale_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="redimensionado"
        )

        self.scale_size_combo = QComboBox()
        self.scale_size_combo.addItems([tr(label) for label in _SIZE_LABELS])
        self.scale_size_combo.currentIndexChanged.connect(self._on_scale_size_changed)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 20000)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1, 20000)
        self._on_scale_size_changed(self.scale_size_combo.currentIndex())

        size_layout = QFormLayout()
        size_layout.addRow(tr("Tamanho:"), self.scale_size_combo)
        size_layout.addRow(tr("Largura:"), self.width_spin)
        size_layout.addRow(tr("Altura:"), self.height_spin)

        apply_button = QPushButton(tr("Redimensionar"))
        self.action_buttons.append(apply_button)
        apply_button.clicked.connect(self._scale)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.scale_output_picker)
        layout.addWidget(QLabel(tr("Novo tamanho da página (pontos):")))
        layout.addLayout(size_layout)
        layout.addWidget(apply_button)
        return widget

    def _on_scale_size_changed(self, index: int):
        label = _SIZE_LABELS[index]
        is_custom = label == CUSTOM_SIZE_LABEL
        self.width_spin.setEnabled(is_custom)
        self.height_spin.setEnabled(is_custom)
        if not is_custom:
            width, height = PAGE_SIZES[label]
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)

    def _margin_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 5000)
        spin.setValue(0)
        return spin

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        self.area_pick_state.set_wanted(self, index == 0)
        self._publish_area()

    def _page_geometry(self, page_index: int) -> PageGeometry | None:
        path = self.session.path()
        if not path:
            return None
        try:
            reader = open_reader(path, purpose=READ)
            return PageGeometry.from_pypdf_page(reader.pages[page_index])
        except Exception:
            return None

    def _on_area_picked(self, page_index: int, left: float, bottom: float, right: float, top: float):
        """A área que deve ficar vira as quatro margens (na orientação da tela, como o
        corte as aplica)."""
        if self.area_pick_state.owner() is not self:
            return
        geometry = self._page_geometry(page_index)
        if geometry is None:
            return
        v_left, v_bottom, v_right, v_top = geometry.user_rect_to_visual((left, bottom, right, top))
        self._crop_page = page_index
        for spin, value in (
            (self.left_spin, v_left),
            (self.bottom_spin, v_bottom),
            (self.right_spin, geometry.width - v_right),
            (self.top_spin, geometry.height - v_top),
        ):
            spin.blockSignals(True)
            spin.setValue(max(0.0, value))
            spin.blockSignals(False)
        self._publish_area()

    def _publish_area(self):
        if not hasattr(self, "top_spin"):
            return
        geometry = self._page_geometry(self._crop_page)
        if geometry is None:
            self.area_pick_state.set_areas(self, [])
            return
        visual = (
            self.left_spin.value(),
            self.bottom_spin.value(),
            geometry.width - self.right_spin.value(),
            geometry.height - self.top_spin.value(),
        )
        self.area_pick_state.set_areas(self, [(self._crop_page, geometry.visual_rect_to_user(visual))], 0)

    def _crop(self):
        input_path = self.session.path()
        output_path = self.crop_output_picker.path()

        if not input_path:
            notify_error(self, tr("Cortar"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Cortar"), tr("Escolha o arquivo de saída."))
            return

        task = call(
            CropPages().run,
            input_path,
            output_path,
            left=self.left_spin.value(),
            bottom=self.bottom_spin.value(),
            right=self.right_spin.value(),
            top=self.top_spin.value(),
        )

        def done(_result):
            self.session.open(output_path)
            notify_success(self, tr("Cortar"), tr("Páginas cortadas com sucesso."))

        run_task(
            self,
            tr("Cortar"),
            task,
            on_success=done,
            error_message=tr("Falha ao cortar páginas: {error}"),
        )

    def _scale(self):
        input_path = self.session.path()
        output_path = self.scale_output_picker.path()

        if not input_path:
            notify_error(self, tr("Redimensionar"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Redimensionar"), tr("Escolha o arquivo de saída."))
            return

        task = call(
            ScalePages().run,
            input_path,
            output_path,
            width=self.width_spin.value(),
            height=self.height_spin.value(),
        )

        def done(_result):
            self.session.open(output_path)
            notify_success(self, tr("Redimensionar"), tr("Páginas redimensionadas com sucesso."))

        run_task(
            self,
            tr("Redimensionar"),
            task,
            on_success=done,
            error_message=tr("Falha ao redimensionar páginas: {error}"),
        )
