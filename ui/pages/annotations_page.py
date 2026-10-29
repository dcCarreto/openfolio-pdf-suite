"""Aba de anotações e marcação: realce, sublinhado, riscado, notas, caneta, formas e
carimbo, e os comentários já gravados no documento (editar, mover, trocar a cor, excluir,
XFDF).

As ações de um comentário só existem nele: o escolhido se abre no lugar, com o texto, a cor,
excluir e "Salvar texto"; com dois ou mais (Ctrl), uma barra acima da lista muda a cor ou
exclui todos de uma vez."""

import re
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.annotations import (
    AddAnnotations,
    AnnotationInfo,
    ExportAnnotationsCSV,
    ListAnnotations,
    MoveAnnotation,
    RecolorAnnotations,
    RemoveAnnotations,
    UpdateAnnotation,
    default_author,
)
from core.xfdf import ExportAnnotationsXFDF, ImportAnnotationsXFDF
from ui import theme
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.errors import show_error
from ui.i18n import plural, tr
from ui.pending_history import PendingHistory
from ui.preferences import preferences, remember_folder_of, start_folder
from ui.tasks import call, run_task
from ui.stamp_library import StampLibrary
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success
from ui.viewer.markup_bar import COLORS, TOOL_LABELS
from ui.viewer.viewer_icons import build_markup_icon, build_more_icon
from ui.widgets.advanced_section import AdvancedSection

_STAMP_TEXTS = ["APROVADO", "CONFIDENCIAL", "RASCUNHO", "REVISADO", "URGENTE"]

_KIND_LABELS = {
    "Text": "Nota",
    "Highlight": "Realce",
    "Underline": "Sublinhado",
    "StrikeOut": "Riscado",
    "Squiggly": "Ondulado",
    "Ink": "Caneta",
    "FreeText": "Texto livre",
    "Stamp": "Carimbo",
    "Square": "Retângulo",
    "Circle": "Círculo",
    "Line": "Linha",
    "Polygon": "Polígono",
    "PolyLine": "Polilinha",
    "Caret": "Inserção",
    "FileAttachment": "Anexo",
}

# O texto desses faz parte do desenho (/AP): trocar /Contents não mudaria o que aparece.
_DRAWN_TEXT_KINDS = {"FreeText", "Stamp"}

# O ícone da ferramenta de marcação que faz cada tipo de anotação gravada.
_KIND_TOOLS = {
    "Text": "note",
    "Highlight": "highlight",
    "Underline": "underline",
    "StrikeOut": "strikeout",
    "Ink": "ink",
    "Square": "square",
    "Circle": "circle",
    "Line": "arrow",
    "Stamp": "stamp",
}

# Dados de cada linha da lista de comentários (o texto do item é o que o leitor de tela lê).
ROW_REF = Qt.ItemDataRole.UserRole  # ("saved", índice em _comments) ou ("pending", índice)
ROW_VIEW = Qt.ItemDataRole.UserRole + 1  # (ferramenta, tipo, página, cor, pendente, trecho)
ROW_OPEN = Qt.ItemDataRole.UserRole + 2  # a altura do editor, na linha aberta no lugar
ROW_HEIGHT = 48
MAX_LIST_ROWS = 10  # mais que isso, a lista rola por dentro
FILTERS = ("all", "pending", "saved")
_XFDF_HELP = "Arquivo só com os comentários, para levá-los a outro leitor de PDF sem enviar o documento."


def format_pdf_date(value: str) -> str:
    """"D:20261019143000-03'00'" -> "19/10/2026 14:30" (vazio se não for uma data do PDF)."""
    match = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", value or "")
    if not match:
        return ""
    year, month, day, hour, minute = match.groups()
    text = f"{day}/{month}/{year}"
    return f"{text} {hour}:{minute or '00'}" if hour else text


def page_text(page_index: int) -> str:
    """"pág. 3": a página de uma marcação, curta."""
    return tr("pág. {number}").format(number=page_index + 1)


def color_dot(color: str | None, size: int = 12) -> QIcon:
    """A bolinha da cor de uma marcação (o botão "Cor" e o menu de cores)."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(theme.tokens()["border_strong"]), 1))
    painter.setBrush(QColor(f"#{color}") if color else QColor(theme.tokens()["raised"]))
    painter.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    painter.end()
    return QIcon(pixmap)


def _tile(tool: str | None, color: str | None) -> QPixmap:
    """A placa de 24 px na cor da marcação, com o ícone do tipo."""
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    _paint_tile(painter, QRect(0, 0, 24, 24), tool, color)
    painter.end()
    return pixmap


def _paint_tile(painter: QPainter, square: QRect, tool: str | None, color: str | None) -> None:
    t = theme.tokens()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(t["border_strong"]), 1))
    painter.setBrush(QColor(f"#{color}") if color else QColor(t["raised"]))
    painter.drawRoundedRect(QRectF(square).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
    if tool:
        build_markup_icon(tool).paint(painter, square.adjusted(4, 4, -4, -4), mode=QIcon.Mode.Normal)


def describe_comment(comment: AnnotationInfo) -> str:
    parts = [
        f"{tr('Página')} {comment.page_index + 1}",
        tr(_KIND_LABELS.get(comment.kind, comment.kind)),
    ]
    parts += [value for value in (comment.author, format_pdf_date(comment.date)) if value]
    text = " · ".join(parts)
    first_line = comment.content.strip().splitlines()[0] if comment.content.strip() else ""
    return f"{text}\n{first_line[:80]}" if first_line else text


class CommentDelegate(QStyledItemDelegate):
    """Uma linha da lista: placa na cor da marcação com o ícone do tipo, o tipo e a página, o
    começo do texto e o estado à direita: "Gravado", ou o selo tracejado "Pendente" (texto, não
    só cor). A linha aberta no lugar é o editor, que cobre o desenho."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if index.data(ROW_OPEN):
            return QSize(0, index.data(ROW_OPEN))
        # A largura é a da lista, não a do texto do item (o do leitor de tela, longo): sem isso a
        # linha passava da lista e o estado à direita ficava cortado.
        return QSize(0, ROW_HEIGHT) if index.data(ROW_VIEW) else size

    def paint(self, painter: QPainter, option, index):
        view = index.data(ROW_VIEW)
        if not view:
            super().paint(painter, option, index)
            return
        if index.data(ROW_OPEN):
            return
        tool, kind, page, color, pending, excerpt = view
        t = theme.tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(0, 1, 0, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected or option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(QPen(QColor(t["accent_line"]), 1) if selected else Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["accent_fill"] if selected else t["hover"]))
            painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        square = QRect(rect.left() + 8, rect.top() + 8, 24, 24)
        _paint_tile(painter, square, tool, color)

        left = square.right() + 10
        base = QFont(option.font)
        small = QFont(base)
        small.setPixelSize(11)
        state_text = tr("Pendente") if pending else tr("Gravado")
        painter.setFont(small)
        state_width = painter.fontMetrics().horizontalAdvance(state_text) + (14 if pending else 0)
        top = QRect(left, rect.top() + 7, rect.right() - left - 8, 18)
        state = QRectF(top.right() - state_width, top.top() + 1, state_width, 16)
        if pending:  # o selo tracejado em warning: existe só na ferramenta, ainda não gravado
            pen = QPen(QColor(t["warning"]), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(state.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            painter.setPen(QColor(t["warning"]))
        else:
            painter.setPen(QColor(t["text3"]))
        painter.drawText(state, Qt.AlignmentFlag.AlignCenter, state_text)

        title = QFont(base)
        title.setPixelSize(13)
        title.setWeight(QFont.Weight.Medium)
        painter.setFont(title)
        painter.setPen(QColor(t["accent_strong" if selected else "text"]))
        room = int(state.left()) - left - 8
        kind_shown = painter.fontMetrics().elidedText(kind, Qt.TextElideMode.ElideRight, room)
        kind_width = painter.fontMetrics().horizontalAdvance(kind_shown)
        painter.drawText(top, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, kind_shown)
        page_font = QFont(base)
        page_font.setPixelSize(12)
        painter.setFont(page_font)
        painter.setPen(QColor(t["text3"]))
        page_rect = QRect(left + kind_width, top.top(), max(0, room - kind_width), 18)
        painter.drawText(page_rect, Qt.AlignmentFlag.AlignVCenter, f" · {page_text(page)}")

        if excerpt:
            painter.setPen(QColor(t["text2"]))
            line = QRect(left, top.bottom() + 2, rect.right() - left - 8, 16)
            shown = painter.fontMetrics().elidedText(excerpt, Qt.TextElideMode.ElideRight, line.width())
            painter.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, shown)
        painter.restore()


class CommentEditor(QFrame):
    """O comentário escolhido, aberto no lugar da linha: o tipo, a página e o autor em cima, o
    texto, e as ações dele (Cor, Excluir e "Salvar texto"). O autor muda pelo menu do item
    (botão direito)."""

    def __init__(self, comment: AnnotationInfo, parent=None):
        super().__init__(parent)
        self.setObjectName("CommentEditor")
        self.comment = comment
        kind = tr(_KIND_LABELS.get(comment.kind, comment.kind))
        tile = QLabel()
        tile.setFixedSize(24, 24)
        tile.setPixmap(_tile(_KIND_TOOLS.get(comment.kind), comment.color))
        self.title = QLabel()
        self.title.setObjectName("CommentEditorTitle")
        self.title.setTextFormat(Qt.TextFormat.RichText)
        author = f" · {comment.author}" if comment.author else ""
        self.title.setText(f"<b>{kind}</b> · {page_text(comment.page_index)}{author}")
        self.title.setMinimumWidth(40)
        state = QLabel(tr("Gravado"))
        state.setProperty("ofRole", "help")
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(tile)
        head.addWidget(self.title, 1)
        head.addWidget(state)

        drawn = comment.kind in _DRAWN_TEXT_KINDS
        self.text_label = QLabel(tr("Texto da nota") if comment.kind == "Text" else tr("Texto"))
        self.text_label.setProperty("ofRole", "field")
        self.text_edit = QPlainTextEdit(comment.content)
        self.text_edit.setFixedHeight(64)
        self.text_edit.setReadOnly(drawn)
        self.text_label.setBuddy(self.text_edit)
        self.text_edit.setAccessibleName(self.text_label.text())
        self.drawn_help = QLabel(tr("O texto deste comentário faz parte do desenho: exclua-o e crie outro."))
        self.drawn_help.setProperty("ofRole", "help")
        self.drawn_help.setWordWrap(True)
        self.drawn_help.setVisible(drawn)
        if drawn:
            self.text_edit.setToolTip(self.drawn_help.text())

        self.color_button = QPushButton(color_dot(comment.color), tr("Cor"))
        self.color_button.setProperty("ofVariant", "ghost")
        self.color_button.setProperty("ofSize", "compact")
        self.delete_button = QPushButton(tr("Excluir"))
        self.delete_button.setProperty("ofVariant", "ghost")
        self.delete_button.setProperty("ofTone", "danger")
        self.delete_button.setProperty("ofSize", "compact")
        self.save_button = QPushButton(tr("Salvar texto"))
        self.save_button.setProperty("ofSize", "compact")
        self.save_button.setEnabled(False)
        self.save_button.setVisible(not drawn)
        self.text_edit.textChanged.connect(
            lambda: self.save_button.setEnabled(self.text_edit.toPlainText() != comment.content)
        )
        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addWidget(self.color_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        actions.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(self.text_label)
        layout.addWidget(self.text_edit)
        layout.addWidget(self.drawn_help)
        layout.addLayout(actions)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)


class AnnotationsPage(QWidget):
    """Permite marcar o PDF aberto (realce, sublinhado, riscado, notas, caneta, carimbo)
    diretamente sobre o visualizador central, e gravar o resultado em um novo arquivo."""

    edits_changed = Signal()  # as pendentes mudaram: desfazer/refazer delas podem ter mudado
    edit_label = "anotação"  # o "Desfazer anotação" do menu
    options_title = "Novas marcações"  # o carimbo e o autor do que ainda vai ser marcado

    def __init__(self, session: DocumentSession, annotation_state: AnnotationState, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.annotation_state = annotation_state
        self._history = PendingHistory(annotation_state, annotation_state.set_pending)
        # Ligado depois do visualizador, que limpa as pendentes ao trocar de arquivo.
        session.path_changed.connect(self._on_document_changed)

        self.source_bar = DocumentSourceBar(session, compact=True)
        # As ferramentas, a cor e a espessura ficam na barra de marcação sobre o visualizador
        # (ui/viewer/markup_bar.py); aqui ficam os comentários, o autor e os carimbos.
        annotation_state.set_tool(annotation_state.active_tool() or "select")
        self._preferences = preferences()
        self.author_edit = QLineEdit()
        author = self._preferences.annotation_author()
        self.author_edit.setText(default_author() if author is None else author)
        self.author_edit.editingFinished.connect(
            lambda: self._preferences.set_annotation_author(self.author_edit.text().strip())
        )
        author_label = QLabel(tr("Autor dos comentários novos"))
        author_label.setObjectName("FieldLabel")
        author_label.setProperty("ofRole", "field")
        author_label.setBuddy(self.author_edit)
        author_help = QLabel(tr("O nome que os leitores de PDF mostram em cada comentário. Fica guardado."))
        author_help.setProperty("ofRole", "help")
        author_help.setWordWrap(True)
        author_box = QWidget()
        author_layout = QVBoxLayout(author_box)
        author_layout.setContentsMargins(0, 0, 0, 0)
        author_layout.setSpacing(8)
        author_layout.addWidget(author_label)
        author_layout.addWidget(self.author_edit)
        author_layout.addWidget(author_help)
        self.advanced = AdvancedSection("AnnotationsPage", "autor dos comentários", author_box)

        self.stamp_label = QLabel(tr("Texto do carimbo"))
        self.stamp_label.setObjectName("FieldLabel")
        self.stamp_label.setProperty("ofRole", "field")
        self.stamp_combo = QComboBox()
        self.stamp_combo.setEditable(True)
        self.stamp_label.setBuddy(self.stamp_combo)
        self.stamp_combo.currentIndexChanged.connect(self._on_stamp_index_changed)
        self.stamp_combo.editTextChanged.connect(self._on_stamp_text_edited)

        self._stamp_library = StampLibrary()
        self._stamp_entries: list[tuple[str, str | None, str | None] | None] = []  # (texto, cor, nome salvo)
        self._reload_stamp_combo()

        self.new_stamp_name_edit = QLineEdit()
        self.new_stamp_name_edit.setPlaceholderText(tr("Nome para salvar este carimbo (opcional)"))
        save_stamp_button = QPushButton(tr("Salvar carimbo"))
        save_stamp_button.setProperty("ofSize", "compact")
        save_stamp_button.clicked.connect(self._save_custom_stamp)
        remove_stamp_button = QPushButton(tr("Remover da lista"))
        remove_stamp_button.setProperty("ofVariant", "ghost")
        remove_stamp_button.setProperty("ofSize", "compact")
        remove_stamp_button.setToolTip(tr("Remove o carimbo salvo que está escolhido"))
        remove_stamp_button.clicked.connect(self._remove_custom_stamp)
        stamp_buttons = QWidget()
        stamp_row = QHBoxLayout(stamp_buttons)
        stamp_row.setContentsMargins(0, 0, 0, 0)
        stamp_row.addWidget(save_stamp_button)
        stamp_row.addWidget(remove_stamp_button)
        stamp_row.addStretch()
        self._stamp_extra_widgets = [self.new_stamp_name_edit, stamp_buttons]

        annotation_state.tool_changed.connect(self._update_stamp_visibility)
        self._update_stamp_visibility()

        # Rodapé do painel: "Descartar 2" as pendentes e "Gravar 2 marcações".
        self.discard_button = QPushButton(tr("Descartar"))
        self.discard_button.setProperty("ofVariant", "ghost")
        self.discard_button.setToolTip(tr("Descarta as marcações ainda não gravadas (Ctrl+Z traz de volta)"))
        self.discard_button.clicked.connect(self.annotation_state.clear_pending)
        self.footer_buttons = [self.discard_button]

        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="anotado"
        )
        self.save_button = QPushButton()
        self.action_buttons.append(self.save_button)
        self.save_button.clicked.connect(self._save)

        # Comentários · 5   [Todas as páginas ▾] [⋯]
        self._comments: list[AnnotationInfo] = []
        self.comments_title = QLabel()
        self.comments_title.setObjectName("CommentsTitle")
        self.comments_title.setProperty("ofRole", "section")
        self.page_filter = QComboBox()
        self.page_filter.setObjectName("CompactCombo")
        self.page_filter.addItems([tr("Todas as páginas"), tr("Página atual")])
        self.page_filter.setAccessibleName(tr("Mostrar os comentários de"))
        self.page_filter.currentIndexChanged.connect(self._apply_filters)
        session.current_page_changed.connect(self._apply_filters)
        self.more_button = QToolButton()
        self.more_button.setObjectName("MoreButton")
        self.more_button.setProperty("ofRole", "icon")
        self.more_button.setIcon(build_more_icon())
        self.more_button.setIconSize(QSize(18, 18))
        self.more_button.setFixedSize(28, 28)
        self.more_button.setToolTip(tr("Exportar e importar comentários"))
        self.more_button.setAccessibleName(tr("Exportar e importar comentários"))
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_button.setMenu(self._build_more_menu())
        self.comments_header = QWidget()
        header = QHBoxLayout(self.comments_header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        header.addWidget(self.comments_title, 1)
        header.addWidget(self.page_filter)
        header.addWidget(self.more_button)

        # Todos · Pendentes 2 · Gravados 3
        self._filter = "all"
        self.filter_buttons: dict[str, QToolButton] = {}
        filter_group = QButtonGroup(self)
        filters = QHBoxLayout()
        filters.setSpacing(6)
        for key in FILTERS:
            pill = QToolButton()
            pill.setProperty("ofRole", "chip")  # 28 px: o alvo mínimo de clique
            pill.setCheckable(True)
            pill.setChecked(key == "all")
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            pill.clicked.connect(lambda _checked=False, k=key: self._set_filter(k))
            filter_group.addButton(pill)
            filters.addWidget(pill)
            self.filter_buttons[key] = pill
        filters.addStretch()

        # Com dois ou mais escolhidos: "3 selecionados · Cor · Excluir 3".
        self.bulk_bar = QFrame()
        self.bulk_bar.setObjectName("BulkBar")
        self.bulk_label = QLabel()
        self.bulk_color_button = QPushButton(tr("Cor"))
        self.bulk_color_button.setProperty("ofVariant", "ghost")
        self.bulk_color_button.setProperty("ofSize", "compact")
        self.bulk_color_button.setMenu(self._color_menu())
        self.bulk_delete_button = QPushButton()
        self.bulk_delete_button.setProperty("ofVariant", "ghost")
        self.bulk_delete_button.setProperty("ofTone", "danger")
        self.bulk_delete_button.setProperty("ofSize", "compact")
        self.bulk_delete_button.clicked.connect(self._remove_comments)
        bulk = QHBoxLayout(self.bulk_bar)
        bulk.setContentsMargins(10, 2, 4, 2)
        bulk.setSpacing(4)
        bulk.addWidget(self.bulk_label, 1)
        bulk.addWidget(self.bulk_color_button)
        bulk.addWidget(self.bulk_delete_button)
        self.bulk_bar.hide()

        self.comments_list = QListWidget()
        self.comments_list.setObjectName("CommentsList")
        self.comments_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.comments_list.setItemDelegate(CommentDelegate(self.comments_list))
        self.comments_list.setMouseTracking(True)
        self.comments_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.comments_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # A lista cresce com as linhas (quem rola é o painel), até MAX_LIST_ROWS.
        self.comments_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.comments_list.itemSelectionChanged.connect(self._on_comment_selected)
        self.editor: CommentEditor | None = None
        move_hint = QLabel(
            tr(
                "Arraste uma marcação na página para movê-la. Selecione várias com Ctrl para mudar a cor "
                "ou excluir de uma vez."
            )
        )
        move_hint.setProperty("ofRole", "help")
        move_hint.setWordWrap(True)
        annotation_state.comment_geometry_requested.connect(self._move_comment)
        session.path_changed.connect(self._load_comments)

        # Comentários (as pendentes e os gravados): uma seção própria do painel, antes das
        # opções (`extra_section`, ver ui/tool_panel.py).
        self.comments_section = QWidget()
        comments = QVBoxLayout(self.comments_section)
        comments.setContentsMargins(0, 0, 0, 0)
        comments.setSpacing(8)
        comments.addLayout(filters)
        comments.addWidget(self.bulk_bar)
        comments.addWidget(self.comments_list)
        comments.addWidget(move_hint)
        self.extra_section = (self.comments_header, self.comments_section)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(self.stamp_label)
        layout.addWidget(self.stamp_combo)
        layout.addWidget(self.new_stamp_name_edit)
        layout.addWidget(stamp_buttons)
        layout.addWidget(self.advanced)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(self.save_button)

        annotation_state.tool_changed.connect(self._update_stamp_visibility)
        self._update_stamp_visibility()
        annotation_state.pending_changed.connect(self._on_pending_changed)
        self._load_comments()
        self._update_pending()

    def _build_more_menu(self) -> QMenu:
        """O "⋯" da lista: exportar (CSV, Excel ou XFDF) e importar comentários."""
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        export = menu.addMenu(tr("Exportar comentários"))
        export.setToolTipsVisible(True)
        formats = (("Planilha CSV...", "csv"), ("Planilha do Excel...", "xlsx"), ("XFDF (só os comentários)...", "xfdf"))
        for label, suffix in formats:
            action = export.addAction(tr(label) if suffix != "xfdf" else f"{tr(label)}  ⓘ")
            if suffix == "xfdf":
                action.setToolTip(tr(_XFDF_HELP))
            action.triggered.connect(lambda _checked=False, s=suffix: self._export(s))
        menu.addAction(tr("Importar comentários (XFDF)...")).triggered.connect(self._import_xfdf)
        return menu

    def _color_menu(self) -> QMenu:
        """As cores para os comentários escolhidos (as mesmas da barra de marcação)."""
        menu = QMenu(self)
        for color, name in COLORS:
            action = QAction(color_dot(color), tr(name), menu)
            action.triggered.connect(lambda _checked=False, c=color: self._recolor_comments(c))
            menu.addAction(action)
        return menu

    # ---- Comentários já gravados ----------------------------------------------------

    def _load_comments(self):
        """Relê a lista a cada versão do documento: as posições em /Annots que ela guarda
        só valem para o arquivo de onde foram lidas."""
        input_path = self.session.path()
        try:
            comments = ListAnnotations().run(input_path) if input_path else []
        except Exception:
            comments = []  # PDF protegido ou ilegível: as outras ferramentas avisam
        self._fill_list(comments)

    def _fill_list(self, comments: list[AnnotationInfo] | None = None):
        """Monta a lista: as marcações pendentes primeiro, depois os comentários gravados."""
        selected = {(c.page_index, c.index) for c in self._selected_comments()}
        if comments is not None:
            self._comments = comments
        pending = self.annotation_state.pending()
        self.comments_list.blockSignals(True)
        self.editor = None  # a lista apaga o editor junto com as linhas
        self.comments_list.clear()
        for number, spec in enumerate(pending):
            tool = spec.kind if spec.kind in TOOL_LABELS else None
            kind = tr(TOOL_LABELS[tool]) if tool else spec.kind
            item = QListWidgetItem(f"{tr('Página')} {spec.page_index + 1} · {kind} · {tr('Pendente')}")
            item.setData(ROW_REF, ("pending", number))
            item.setData(ROW_VIEW, (tool, kind, spec.page_index, spec.color, True, spec.text or ""))
            self.comments_list.addItem(item)
        for number, comment in enumerate(self._comments):
            kind = tr(_KIND_LABELS.get(comment.kind, comment.kind))
            excerpt = comment.content.strip().splitlines()[0] if comment.content.strip() else ""
            item = QListWidgetItem(describe_comment(comment))
            item.setData(ROW_REF, ("saved", number))
            item.setData(
                ROW_VIEW, (_KIND_TOOLS.get(comment.kind), kind, comment.page_index, comment.color, False, excerpt)
            )
            self.comments_list.addItem(item)
            if (comment.page_index, comment.index) in selected:
                item.setSelected(True)
        if not pending and not self._comments:
            empty = QListWidgetItem(tr("Nenhum comentário ainda. As marcações que você fizer na página aparecem aqui."))
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            empty.setForeground(theme.color("text3"))
            self.comments_list.addItem(empty)
        count = len(pending) + len(self._comments)
        self.comments_title.setText(tr("Comentários · {count}").format(count=count))
        self.filter_buttons["all"].setText(tr("Todos"))
        self.filter_buttons["pending"].setText(tr("Pendentes {count}").format(count=len(pending)))
        self.filter_buttons["saved"].setText(tr("Gravados {count}").format(count=len(self._comments)))
        self.comments_list.blockSignals(False)
        self._apply_filters()
        self._on_comment_selected()

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self._apply_filters()

    def _apply_filters(self, *_args):
        """O filtro em pílulas (todos, pendentes, gravados) e o de página ("Página atual": só
        as marcações da página que o visualizador mostra)."""
        only_current = self.page_filter.currentIndex() == 1
        current = self.session.current_page()
        for row in range(self.comments_list.count()):
            view = self.comments_list.item(row).data(ROW_VIEW)
            hidden = bool(view) and (
                (only_current and view[2] != current)
                or (self._filter == "pending" and not view[4])
                or (self._filter == "saved" and view[4])
            )
            self.comments_list.setRowHidden(row, hidden)
        self._fit_list()

    def _fit_list(self) -> None:
        """A altura da lista é a das linhas à mostra (com a aberta no lugar), até MAX_LIST_ROWS."""
        rows = [row for row in range(self.comments_list.count()) if not self.comments_list.isRowHidden(row)]
        heights = [self.comments_list.sizeHintForRow(row) for row in rows]
        total = sum(heights) or ROW_HEIGHT
        limit = MAX_LIST_ROWS * ROW_HEIGHT + max([0, *heights]) - ROW_HEIGHT
        frame = 2 * self.comments_list.frameWidth()
        self.comments_list.setFixedHeight(min(total, limit) + frame)

    def _apply_page_filter(self):  # nome antigo
        self._apply_filters()

    def _selected_refs(self) -> list[tuple[str, int]]:
        refs = [item.data(ROW_REF) for item in self.comments_list.selectedItems()]
        return sorted(ref for ref in refs if ref)

    def _selected_comments(self) -> list[AnnotationInfo]:
        refs = self._selected_refs()
        return [self._comments[n] for kind, n in refs if kind == "saved" and n < len(self._comments)]

    def _item_of(self, comment: AnnotationInfo) -> QListWidgetItem | None:
        number = self._comments.index(comment)
        for row in range(self.comments_list.count()):
            if self.comments_list.item(row).data(ROW_REF) == ("saved", number):
                return self.comments_list.item(row)
        return None

    def _close_editor(self) -> None:
        if self.editor is None:
            return
        for row in range(self.comments_list.count()):
            item = self.comments_list.item(row)
            if item.data(ROW_OPEN):
                item.setData(ROW_OPEN, None)
                self.comments_list.removeItemWidget(item)  # a lista apaga o editor
        self.editor = None

    def _open_editor(self, comment: AnnotationInfo) -> None:
        """Abre o comentário no lugar da linha dele, com as ações que só ele tem."""
        item = self._item_of(comment)
        if item is None:
            return
        editor = CommentEditor(comment)
        editor.save_button.clicked.connect(lambda: self._update_comment())
        editor.delete_button.clicked.connect(self._remove_comments)
        editor.color_button.setMenu(self._color_menu())
        editor.customContextMenuRequested.connect(lambda pos: self._editor_menu(editor, pos))
        self.comments_list.setItemWidget(item, editor)
        width = self.comments_list.viewport().width()
        height = editor.heightForWidth(width) if editor.hasHeightForWidth() else -1
        item.setData(ROW_OPEN, (height if height > 0 else editor.sizeHint().height()) + 2)
        self.editor = editor
        self.comments_list.doItemsLayout()  # a linha mudou de altura
        self._fit_list()
        self.comments_list.scrollToItem(item)

    def _editor_menu(self, editor: CommentEditor, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction(tr("Mudar o autor...")).triggered.connect(self._ask_author)
        menu.exec(editor.mapToGlobal(pos))

    def _ask_author(self) -> None:
        selected = self._selected_comments()
        if len(selected) != 1:
            return
        author, ok = QInputDialog.getText(self, tr("Mudar o autor"), tr("Autor do comentário"), text=selected[0].author)
        if ok:
            self._update_comment(author=author.strip())

    @property
    def comment_text_edit(self) -> QPlainTextEdit | None:
        """O campo do texto do comentário aberto (None sem um escolhido só)."""
        return self.editor.text_edit if self.editor is not None else None

    def _on_comment_selected(self):
        selected = self._selected_comments()
        single = selected[0] if len(selected) == 1 and len(self._selected_refs()) == 1 else None
        self._close_editor()
        if single is not None:
            self._open_editor(single)
        many = len(selected) >= 2
        self.bulk_bar.setVisible(many)
        if many:
            self.bulk_label.setText(plural(len(selected), "1 selecionado", "{count} selecionados"))
            self.bulk_delete_button.setText(tr("Excluir {count}").format(count=len(selected)))
        self.annotation_state.set_selected_comment(
            (single.page_index, single.rect) if single is not None and single.rect else None
        )
        refs = self._selected_refs()
        if len(refs) == 1 and refs[0][0] == "pending":  # uma pendente: mostra a página dela
            pending = self.annotation_state.pending()
            if refs[0][1] < len(pending):
                self.annotation_state.request_page(pending[refs[0][1]].page_index)

    def _apply_to_document(self, title: str, operation, message):
        """Roda `operation(entrada, saída)` numa versão nova do documento de trabalho
        (Ctrl+Z desfaz) e mostra `message(resultado)`."""
        input_path = self.session.path()
        if not input_path:
            notify_error(self, title, tr("Abra um PDF para começar."))
            return
        output_path = self.session.new_version_path()

        def done(result):
            self.session.open(output_path)
            text = message(result)
            if text:
                notify_success(self, title, text)

        run_task(self, title, call(operation, input_path, output_path), on_success=done)

    def _update_comment(self, author: str | None = None):
        """"Salvar texto" do comentário aberto; com `author`, muda também o autor (menu do item)."""
        selected = self._selected_comments()
        if len(selected) != 1:
            return
        comment = selected[0]
        editor = self.editor
        if comment.kind in _DRAWN_TEXT_KINDS or editor is None:
            content = comment.content
        else:
            content = editor.text_edit.toPlainText()
        author = comment.author if author is None else author
        self._apply_to_document(
            tr("Editar comentário"),
            lambda source, output: UpdateAnnotation().run(
                source, output, comment.page_index, comment.index, content, author
            ),
            message=lambda _result: "",
        )

    def _remove_comments(self):
        items = [(c.page_index, c.index) for c in self._selected_comments()]
        if not items:
            return
        self._apply_to_document(
            tr("Excluir comentários"),
            lambda source, output: RemoveAnnotations().run(source, output, items),
            message=lambda count: plural(
                count, "1 comentário excluído, com as respostas.", "{count} comentários excluídos, com as respostas."
            ),
        )

    def _recolor_comments(self, color: str | None = None):
        """Muda a cor dos escolhidos (sem `color`, para a cor da barra de marcação)."""
        items = [(c.page_index, c.index) for c in self._selected_comments()]
        if not items:
            return
        color = color or self.annotation_state.active_color()

        def message(result):
            changed, skipped = result
            text = plural(changed, "Cor trocada em 1 comentário.", "Cor trocada em {count} comentários.")
            if skipped:
                text += " " + plural(
                    skipped,
                    "1 ficou como estava: carimbos, textos livres e polígonos têm o desenho fixo.",
                    "{count} ficaram como estavam: carimbos, textos livres e polígonos têm o desenho fixo.",
                )
            return text

        self._apply_to_document(
            tr("Trocar a cor"),
            lambda source, output: RecolorAnnotations().run(source, output, items, color),
            message=message,
        )

    def _move_comment(self, page_index: int, rect):
        selected = self._selected_comments()
        if len(selected) != 1 or selected[0].page_index != page_index:
            return
        comment = selected[0]
        self._apply_to_document(
            tr("Mover comentário"),
            lambda source, output: MoveAnnotation().run(source, output, comment.page_index, comment.index, rect),
            message=lambda _result: "",
        )

    def _import_xfdf(self):
        if not self.session.path():
            notify_error(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        xfdf_path, _ = QFileDialog.getOpenFileName(
            self, tr("Importar comentários (XFDF)"), start_folder(), "XFDF (*.xfdf);;XML (*.xml)"
        )
        if not xfdf_path:
            return
        remember_folder_of(xfdf_path)

        def message(result):
            imported, skipped = result
            text = plural(imported, "1 comentário importado.", "{count} comentários importados.")
            if skipped:
                text += " " + plural(
                    skipped,
                    "1 ficou de fora: tipo não suportado, página que não existe ou dados inválidos.",
                    "{count} ficaram de fora: tipo não suportado, página que não existe ou dados inválidos.",
                )
            return text

        self._apply_to_document(
            tr("Importar comentários (XFDF)"),
            lambda source, output: ImportAnnotationsXFDF().run(source, xfdf_path, output),
            message=message,
        )

    def _reload_stamp_combo(self, select_name: str | None = None):
        self.stamp_combo.blockSignals(True)
        self.stamp_combo.clear()
        self._stamp_entries = []
        for text in _STAMP_TEXTS:
            label = tr(text)
            self.stamp_combo.addItem(label)
            self._stamp_entries.append((label, None, None))

        custom_stamps = self._stamp_library.list_stamps()
        if custom_stamps:
            self.stamp_combo.insertSeparator(self.stamp_combo.count())
            self._stamp_entries.append(None)
            for stamp in custom_stamps:
                self.stamp_combo.addItem(stamp.name)
                self._stamp_entries.append((stamp.text, stamp.color, stamp.name))
        self.stamp_combo.blockSignals(False)

        target_index = 0
        if select_name is not None:
            found = self.stamp_combo.findText(select_name)
            if found >= 0:
                target_index = found
        self.stamp_combo.setCurrentIndex(target_index)
        self._apply_stamp_entry(target_index)

    def _apply_stamp_entry(self, index: int):
        if not (0 <= index < len(self._stamp_entries)):
            return
        entry = self._stamp_entries[index]
        if entry is None:
            return
        text, color, _name = entry
        self.annotation_state.set_stamp_text(text)
        if color is not None:
            self.annotation_state.set_color(color)  # a barra de marcação acompanha

    def _on_stamp_index_changed(self, index: int):
        self._apply_stamp_entry(index)

    def _on_stamp_text_edited(self, text: str):
        self.annotation_state.set_stamp_text(text)

    def _save_custom_stamp(self):
        text = self.stamp_combo.currentText().strip()
        if not text:
            notify_error(self, tr("Anotações"), tr("Digite o texto do carimbo antes de salvar."))
            return
        name = self.new_stamp_name_edit.text().strip() or text

        try:
            self._stamp_library.add_stamp(name, text, color=self.annotation_state.active_color())
        except Exception as exc:
            show_error(self, tr("Anotações"), tr("Falha ao salvar carimbo: {error}"), exc)
            return

        self.new_stamp_name_edit.clear()
        self._reload_stamp_combo(select_name=name)
        notify_success(self, tr("Anotações"), tr("Carimbo salvo com sucesso."))

    def _remove_custom_stamp(self):
        index = self.stamp_combo.currentIndex()
        entry = self._stamp_entries[index] if 0 <= index < len(self._stamp_entries) else None
        if entry is None or entry[2] is None:
            notify_error(
                self, tr("Anotações"), tr("Selecione um carimbo customizado para remover.")
            )
            return

        # Pelo nome salvo: o combo é editável, e o texto dele pode já ter sido alterado.
        self._stamp_library.remove_stamp(entry[2])
        self._reload_stamp_combo()

    def _update_stamp_visibility(self):
        is_stamp = self.annotation_state.active_tool() == "stamp"
        self.stamp_label.setVisible(is_stamp)
        self.stamp_combo.setVisible(is_stamp)
        for widget in self._stamp_extra_widgets:
            widget.setVisible(is_stamp)

    def _update_pending(self):
        count = len(self.annotation_state.pending())
        if count:
            self.save_button.setText(plural(count, "Gravar 1 marcação", "Gravar {count} marcações"))
        else:
            self.save_button.setText(tr("Nada para gravar"))
        self.save_button.setEnabled(count > 0)
        self.discard_button.setText(tr("Descartar {count}").format(count=count) if count else tr("Descartar"))
        self.discard_button.setEnabled(count > 0)
        self.discard_button.setVisible(count > 0)

    def _on_pending_changed(self):
        self._history.changed()
        self._update_pending()
        self._fill_list()
        self.edits_changed.emit()  # o painel atualiza o botão do rodapé

    def _on_document_changed(self):
        self._history.reset()
        self.edits_changed.emit()

    # Ctrl+Z / Ctrl+Y da janela: as anotações pendentes vêm antes das versões do documento.

    def can_undo_edit(self) -> bool:
        return self._history.can_undo()

    def can_redo_edit(self) -> bool:
        return self._history.can_redo()

    def undo_edit(self) -> None:
        self._history.undo()

    def redo_edit(self) -> None:
        self._history.redo()

    def save_to_document(self):
        """"Gravar" da barra de marcação: as pendentes viram uma versão do documento aberto."""
        self._save(self.session.new_version_path() if self.session.path() else "")

    def _save(self, output_path: str | None = None):
        input_path = self.session.path()
        output_path = self.output_picker.path() if output_path is None else output_path
        pending = self.annotation_state.pending()

        if not input_path:
            notify_error(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Anotações"), tr("Escolha o arquivo de saída."))
            return
        if not pending:
            notify_error(
                self, tr("Anotações"), tr("Adicione pelo menos uma anotação antes de salvar.")
            )
            return

        author = self.author_edit.text().strip()
        self._preferences.set_annotation_author(author)
        task = call(AddAnnotations().run, input_path, output_path, pending, author=author)

        def done(_result):
            self.annotation_state.clear_pending()
            self.session.open(output_path)
            notify_success(
                self, tr("Anotações"), plural(len(pending), "1 marcação gravada.", "{count} marcações gravadas.")
            )

        run_task(
            self,
            tr("Gravar marcações"),  # o nome do passo no Ctrl+Z
            task,
            on_success=done,
            error_message=tr("Falha ao salvar anotações: {error}"),
        )

    def _export(self, suffix: str):
        """Exportar comentários (do "⋯"): CSV, Excel ou XFDF, num arquivo escolhido agora."""
        input_path = self.session.path()
        if not input_path:
            notify_error(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        stem = Path(self.session.source_path() or input_path).stem
        filters = {"csv": "CSV (*.csv)", "xlsx": "Excel (*.xlsx)", "xfdf": "XFDF (*.xfdf)"}
        suggested = str(Path(start_folder()) / f"{stem} - {tr('comentários')}.{suffix}")
        output_path, _ = QFileDialog.getSaveFileName(self, tr("Exportar comentários"), suggested, filters[suffix])
        if not output_path:
            return
        remember_folder_of(output_path)
        if not output_path.lower().endswith(f".{suffix}"):
            output_path += f".{suffix}"

        if suffix == "xfdf":
            task = call(ExportAnnotationsXFDF().run, input_path, output_path)
        else:
            task = call(lambda *paths: (ExportAnnotationsCSV().run(*paths), 0), input_path, output_path)

        def done(result):
            count, skipped = result
            text = plural(count, "1 comentário exportado.", "{count} comentários exportados.")
            if skipped:
                text += " " + plural(
                    skipped,
                    "1 de tipo que o XFDF não leva (anexo, som...) ficou de fora.",
                    "{count} de tipo que o XFDF não leva (anexo, som...) ficaram de fora.",
                )
            notify_success(self, tr("Anotações"), text)

        run_task(
            self,
            tr("Exportar comentários"),
            task,
            on_success=done,
            error_message=tr("Não foi possível exportar os comentários.") + "\n{error}",
        )
