"""Aba Preencher e assinar (A04): texto, data, assinatura e iniciais colocados arrastando
no visualizador, sem certificado.

Escolha o que colocar e arraste na página para marcar a área; cada área entra na lista e
aparece desenhada no visualizador. "Aplicar" grava tudo no documento de trabalho numa versão
só (`FillAndSign`), que Ctrl+Z desfaz. A assinatura e as iniciais (desenhadas aqui ou de uma
imagem) ficam guardadas nas preferências para as próximas vezes.
"""

from PySide6.QtCore import QBuffer, QByteArray, QDate, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.fill_sign import FillAndSign, FillItem, fit_text_size
from core.fonts import SANS, font_file
from ui.area_pick_state import AreaPickState
from ui.i18n import tr
from ui.preferences import preferences, remember_folder_of, start_folder
from ui.tasks import run_task

_KINDS = ["Texto", "Data", "Assinatura", "Iniciais"]
_TEXT, _DATE, _SIGNATURE, _INITIALS = range(4)
_IMAGE_KEYS = {_SIGNATURE: "signature", _INITIALS: "initials"}
_INK = QColor("#1f2a6b")
_DATE_FORMAT = "dd/MM/yyyy"


_preview_family = None


def _sans_family() -> str:
    """A mesma fonte embutida que vai para o PDF, carregada no Qt para a prévia."""
    global _preview_family
    if _preview_family is None:
        families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(font_file(SANS))))
        _preview_family = families[0] if families else ""
    return _preview_family


def paint_fill_item(painter: QPainter, rect: QRectF, text: str = "", image: bytes = b"") -> None:
    """Desenha na tela o que `FillAndSign` vai gravar na área: a imagem ajustada sem
    distorcer e centralizada, ou o texto em uma linha com o mesmo tamanho calculado."""
    if image:
        picture = QImage.fromData(image)
        if picture.isNull() or rect.isEmpty():
            return
        fitted = picture.size().scaled(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF(0, 0, fitted.width(), fitted.height())
        target.moveCenter(rect.center())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, picture)
        return
    if not text.strip() or rect.isEmpty():
        return
    size = fit_text_size(text, rect.width(), rect.height())
    font = QFont(_sans_family())
    font.setPixelSize(100)  # desenhado em escala: o tamanho calculado não precisa ser inteiro
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    painter.setPen(Qt.GlobalColor.black)
    painter.translate(rect.left(), rect.bottom() - (rect.height() - size * 0.7) / 2)
    painter.scale(size / 100, size / 100)
    painter.drawText(QPointF(0, 0), text)


class SignaturePad(QWidget):
    """Área branca para desenhar a assinatura com o mouse ou a caneta."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 160)
        self._strokes: list[list[QPointF]] = []

    def is_empty(self) -> bool:
        return not any(len(stroke) > 1 for stroke in self._strokes)

    def clear(self) -> None:
        self._strokes = []
        self.update()

    def add_stroke(self, points: list[QPointF]) -> None:
        self._strokes.append(list(points))
        self.update()

    def mousePressEvent(self, event):
        self.add_stroke([event.position()])

    def mouseMoveEvent(self, event):
        if self._strokes and event.buttons():
            self._strokes[-1].append(event.position())
            self.update()

    def _paint_strokes(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(_INK, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        for stroke in self._strokes:
            path = QPainterPath(stroke[0])
            for point in stroke[1:]:
                path.lineTo(point)
            painter.drawPath(path)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)
        painter.setPen(QPen(QColor("#b0b0b0"), 1))
        baseline = self.height() * 0.75
        painter.drawLine(QPointF(16, baseline), QPointF(self.width() - 16, baseline))
        self._paint_strokes(painter)
        painter.end()

    def to_png(self) -> bytes:
        """O desenho com fundo transparente, recortado em volta dos traços, em resolução
        três vezes maior que a tela (para não ficar serrilhado no PDF)."""
        points = [point for stroke in self._strokes for point in stroke]
        if self.is_empty():
            return b""
        margin, scale = 4, 3
        xs, ys = [p.x() for p in points], [p.y() for p in points]
        area = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).adjusted(-margin, -margin, margin, margin)
        image = QImage(int(area.width() * scale) + 1, int(area.height() * scale) + 1, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(scale, scale)
        painter.translate(-area.topLeft())
        self._paint_strokes(painter)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")  # type: ignore[call-overload]  # o stub pede bytes, o PySide6 só aceita texto
        return bytes(data.data())


class SignatureDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.pad = SignaturePad()
        clear_button = QPushButton(tr("Limpar"))
        clear_button.clicked.connect(self.pad.clear)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(clear_button, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Desenhe com o mouse ou a caneta:")))
        layout.addWidget(self.pad)
        layout.addWidget(buttons)


class FillSignPage(QWidget):
    def __init__(self, session, area_pick_state: AreaPickState | None = None, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.area_pick_state = area_pick_state or AreaPickState()
        self._items: list[FillItem] = []

        self.kind_combo = QComboBox()
        self.kind_combo.addItems([tr(kind) for kind in _KINDS])
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText(tr("Texto a colocar na página"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat(_DATE_FORMAT)

        image_panel = QWidget()
        image_layout = QVBoxLayout(image_panel)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setWordWrap(True)  # o aviso de "nada guardado" não alarga o painel
        self.image_preview.setFixedHeight(70)
        self.image_preview.setStyleSheet("background-color: white; color: #707070; border: 1px solid #b0b0b0;")
        self.draw_button = QPushButton(tr("Desenhar..."))
        self.draw_button.clicked.connect(self._draw_image)
        self.image_button = QPushButton(tr("Imagem..."))
        self.image_button.setToolTip(tr("Usa uma imagem PNG ou JPEG (de preferência com fundo transparente)."))
        self.image_button.clicked.connect(self._choose_image)
        image_buttons = QHBoxLayout()
        image_buttons.addWidget(self.draw_button)
        image_buttons.addWidget(self.image_button)
        image_layout.addWidget(self.image_preview)
        image_layout.addLayout(image_buttons)

        self.content_stack = QStackedWidget()
        for widget in (self.text_edit, self.date_edit, image_panel):
            self.content_stack.addWidget(widget)

        hint = QLabel(tr("Arraste no visualizador para marcar onde colocar; cada área recebe o item escolhido acima."))
        hint.setWordWrap(True)

        self.items_list = QListWidget()
        self.items_list.currentRowChanged.connect(lambda _row: self._publish_areas())
        self.remove_button = QPushButton(tr("Remover"))
        self.remove_button.clicked.connect(self.remove_selected)
        self.apply_button = QPushButton(tr("Aplicar"))
        self.action_buttons.append(self.apply_button)
        self.apply_button.clicked.connect(self._apply)
        item_buttons = QHBoxLayout()
        item_buttons.addWidget(self.remove_button)
        item_buttons.addStretch()
        item_buttons.addWidget(self.apply_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        note = QLabel(tr("O que é colocado aqui entra no conteúdo da página. Não é assinatura digital: para isso, use a aba Assinatura digital."))
        note.setWordWrap(True)
        note.setObjectName("pageSubtitle")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("O que colocar:")))
        layout.addWidget(self.kind_combo)
        layout.addWidget(self.content_stack)
        layout.addWidget(hint)
        layout.addWidget(self.items_list, 1)
        layout.addLayout(item_buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(note)

        self.area_pick_state.area_picked.connect(self._on_area_picked)
        self.area_pick_state.set_wanted(self, True)
        self.area_pick_state.set_preview(self, self._paint_preview)
        # As áreas valem para a versão do documento em que foram marcadas.
        session.path_changed.connect(self._clear_items)
        self._on_kind_changed(_TEXT)

    def items(self) -> list[FillItem]:
        return list(self._items)

    def _on_kind_changed(self, kind: int) -> None:
        self.content_stack.setCurrentIndex(min(kind, 2))
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        kind = self.kind_combo.currentIndex()
        if kind not in _IMAGE_KEYS:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(preferences().saved_image(_IMAGE_KEYS[kind])):
            self.image_preview.setPixmap(
                pixmap.scaled(260, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.image_preview.setText(tr("Nada guardado ainda: desenhe ou escolha uma imagem."))

    def store_image(self, kind: int, data: bytes) -> bool:
        if QImage.fromData(data).isNull():
            self.status_label.setText(tr("Não foi possível ler a imagem."))
            return False
        preferences().set_saved_image(_IMAGE_KEYS[kind], data)
        self._refresh_preview()
        return True

    def _draw_image(self) -> None:
        kind = self.kind_combo.currentIndex()
        dialog = SignatureDialog(tr(_KINDS[kind]), self)
        if dialog.exec() == QDialog.DialogCode.Accepted and not dialog.pad.is_empty():
            self.store_image(kind, dialog.pad.to_png())

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Selecionar arquivo"), start_folder(), tr("Imagens") + " (*.png *.jpg *.jpeg)"
        )
        if not path:
            return
        remember_folder_of(path)
        with open(path, "rb") as file:
            self.store_image(self.kind_combo.currentIndex(), file.read())

    def _current_content(self) -> tuple[str, bytes]:
        """(texto, imagem) do item escolhido agora; os dois vazios se falta conteúdo."""
        kind = self.kind_combo.currentIndex()
        if kind == _TEXT:
            return self.text_edit.text().strip(), b""
        if kind == _DATE:
            return self.date_edit.date().toString(_DATE_FORMAT), b""
        return "", preferences().saved_image(_IMAGE_KEYS[kind])

    def _paint_preview(self, painter: QPainter, rect: QRectF, number: int | None) -> None:
        if number is None:
            text, image = self._current_content()
        elif 0 <= number < len(self._items):
            text, image = self._items[number].text, self._items[number].image
        else:
            return
        paint_fill_item(painter, rect, text, image)

    def _on_area_picked(self, page_index: int, left: float, bottom: float, right: float, top: float) -> None:
        if self.area_pick_state.owner() is not self:
            return
        kind = self.kind_combo.currentIndex()
        text, image = self._current_content()
        if not text and not image:
            self.status_label.setText(
                tr("Digite o texto antes de marcar a área.")
                if kind == _TEXT
                else tr("Desenhe ou escolha a imagem antes de marcar a área.")
            )
            return
        item = FillItem(page_index, (left, bottom, right, top), text=text, image=image)
        description = text or tr(_KINDS[kind])
        self._items.append(item)
        self.items_list.addItem(f"{tr('Página {number}').format(number=page_index + 1)} · {description}")
        self.items_list.setCurrentRow(len(self._items) - 1)
        self.status_label.clear()
        self._publish_areas()

    def remove_selected(self) -> None:
        row = self.items_list.currentRow()
        if row < 0:
            return
        del self._items[row]
        self.items_list.takeItem(row)
        self._publish_areas()

    def _clear_items(self) -> None:
        self._items = []
        self.items_list.clear()
        self._publish_areas()

    def _publish_areas(self) -> None:
        row = self.items_list.currentRow()
        self.area_pick_state.set_areas(
            self, [(item.page_index, item.rect) for item in self._items], row if row >= 0 else None
        )
        self.remove_button.setEnabled(row >= 0)
        self.apply_button.setEnabled(bool(self._items))

    def _apply(self) -> None:
        input_path = self.session.path()
        if not input_path or not self._items:
            return
        items = self.items()
        output_path = self.session.new_version_path()
        run_task(
            self,
            tr("Preencher e assinar"),
            lambda _progress: FillAndSign().run(input_path, output_path, items),
            on_success=lambda _result: self.session.open(output_path),
        )
