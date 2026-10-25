"""Aba de anotações e marcação: realce, sublinhado, riscado, notas, caneta, formas e
carimbo, e os comentários já gravados no documento (editar, mover, trocar a cor, remover,
XFDF)."""

import re

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
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
from ui.i18n import tr
from ui.pending_history import PendingHistory
from ui.preferences import preferences, remember_folder_of, start_folder
from ui.tasks import call, run_task
from ui.stamp_library import StampLibrary
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success
from ui.viewer.markup_bar import TOOL_LABELS
from ui.viewer.viewer_icons import build_markup_icon

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
ROW_HEIGHT = 52


def format_pdf_date(value: str) -> str:
    """"D:20261019143000-03'00'" -> "19/10/2026 14:30" (vazio se não for uma data do PDF)."""
    match = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", value or "")
    if not match:
        return ""
    year, month, day, hour, minute = match.groups()
    text = f"{day}/{month}/{year}"
    return f"{text} {hour}:{minute or '00'}" if hour else text


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
    """Uma linha da lista: quadrado na cor da marcação com o ícone do tipo, tipo, página, selo
    "Pendente" ou "Gravado" (texto, não só cor) e o começo do texto."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), ROW_HEIGHT if index.data(ROW_VIEW) else size.height())

    def paint(self, painter: QPainter, option, index):
        view = index.data(ROW_VIEW)
        if not view:
            super().paint(painter, option, index)
            return
        tool, kind, page, color, pending, excerpt = view
        t = theme.tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 2, -4, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected or option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(QPen(QColor(t["accent_line"]), 1) if selected else Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["accent_fill"] if selected else t["raised"]))
            painter.drawRoundedRect(QRectF(rect), 6, 6)

        square = QRect(rect.left() + 8, rect.top() + (rect.height() - 24) // 2, 24, 24)
        painter.setPen(QPen(QColor(t["border_strong"]), 1))
        painter.setBrush(QColor(f"#{color}") if color else QColor(t["raised"]))
        painter.drawRoundedRect(QRectF(square), 5, 5)
        if tool:
            build_markup_icon(tool).paint(painter, square.adjusted(4, 4, -4, -4), mode=QIcon.Mode.Normal)

        left = square.right() + 10
        base = QFont(option.font)
        title = QFont(base)
        title.setPixelSize(12)
        title.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title)
        painter.setPen(QColor(t["text"]))
        top = QRect(left, rect.top() + 7, rect.right() - left - 8, 18)
        kind_width = painter.fontMetrics().horizontalAdvance(kind)
        painter.drawText(top, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, kind)

        small = QFont(base)
        small.setPixelSize(11)
        painter.setFont(small)
        painter.setPen(QColor(t["text3"]))
        page_text = f"{tr('Página')} {page + 1}"
        page_left = left + kind_width + 8
        painter.drawText(QRect(page_left, top.top(), top.right() - page_left, 18), Qt.AlignmentFlag.AlignVCenter, page_text)

        # Selo à direita: "Pendente" no acento, "Gravado" neutro.
        badge_text = tr("Pendente") if pending else tr("Gravado")
        badge_width = painter.fontMetrics().horizontalAdvance(badge_text) + 12
        badge = QRectF(top.right() - badge_width, top.top() + 1, badge_width, 16)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(t["accent_line" if pending else "border_strong"]), 1))
        painter.drawRoundedRect(badge, 4, 4)
        painter.setPen(QColor(t["accent_strong" if pending else "text2"]))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, badge_text)

        if excerpt:
            text = QFont(base)
            text.setPixelSize(12)
            painter.setFont(text)
            painter.setPen(QColor(t["text2"]))
            line = QRect(left, top.bottom() + 3, rect.right() - left - 8, 16)
            shown = painter.fontMetrics().elidedText(excerpt, Qt.TextElideMode.ElideRight, line.width())
            painter.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, shown)
        painter.restore()


class AnnotationsPage(QWidget):
    """Permite marcar o PDF aberto (realce, sublinhado, riscado, notas, caneta, carimbo)
    diretamente sobre o visualizador central, e gravar o resultado em um novo arquivo."""

    edits_changed = Signal()  # as pendentes mudaram: desfazer/refazer delas podem ter mudado
    edit_label = "anotação"  # o "Desfazer anotação" do menu

    def __init__(self, session: DocumentSession, annotation_state: AnnotationState, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.annotation_state = annotation_state
        self._history = PendingHistory(annotation_state, annotation_state.set_pending)
        # Ligado depois do visualizador, que limpa as pendentes ao trocar de arquivo.
        session.path_changed.connect(self._on_document_changed)

        self.source_bar = DocumentSourceBar(session)
        # As ferramentas, a cor e a espessura ficam na barra de marcação sobre o visualizador
        # (ui/viewer/markup_bar.py); aqui ficam os comentários, o autor e os carimbos.
        annotation_state.set_tool(annotation_state.active_tool() or "select")
        self._preferences = preferences()
        self.author_edit = QLineEdit()
        author = self._preferences.annotation_author()
        self.author_edit.setText(default_author() if author is None else author)
        self.author_edit.setToolTip(tr("O nome que os leitores mostram em cada comentário novo. Fica guardado."))
        self.author_edit.editingFinished.connect(
            lambda: self._preferences.set_annotation_author(self.author_edit.text().strip())
        )
        drawing_form = QFormLayout()
        drawing_form.addRow(tr("Autor:"), self.author_edit)

        self.stamp_label = QLabel(tr("Texto do carimbo:"))
        self.stamp_combo = QComboBox()
        self.stamp_combo.setEditable(True)
        self.stamp_combo.currentIndexChanged.connect(self._on_stamp_index_changed)
        self.stamp_combo.editTextChanged.connect(self._on_stamp_text_edited)

        self._stamp_library = StampLibrary()
        self._stamp_entries: list[tuple[str, str | None, str | None] | None] = []  # (texto, cor, nome salvo)
        self._reload_stamp_combo()

        self.new_stamp_name_edit = QLineEdit()
        self.new_stamp_name_edit.setPlaceholderText(tr("Nome para salvar este carimbo (opcional)"))
        save_stamp_button = QPushButton(tr("Salvar carimbo customizado"))
        save_stamp_button.clicked.connect(self._save_custom_stamp)
        remove_stamp_button = QPushButton(tr("Remover carimbo customizado selecionado"))
        remove_stamp_button.clicked.connect(self._remove_custom_stamp)
        self._stamp_extra_widgets = [
            self.new_stamp_name_edit,
            save_stamp_button,
            remove_stamp_button,
        ]

        annotation_state.tool_changed.connect(self._update_stamp_visibility)
        self._update_stamp_visibility()

        # Rodapé do painel: "Descartar" as pendentes e "Gravar N marcações".
        self.discard_button = QPushButton(tr("Descartar"))
        self.discard_button.setToolTip(tr("Descarta as marcações ainda não gravadas (Ctrl+Z traz de volta)"))
        self.discard_button.clicked.connect(self.annotation_state.clear_pending)
        self.footer_buttons = [self.discard_button]

        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="anotado"
        )
        self.save_button = QPushButton()
        self.action_buttons.append(self.save_button)
        self.save_button.clicked.connect(self._save)

        self._comments: list[AnnotationInfo] = []
        self.comments_title = QLabel()
        self.comments_title.setObjectName("CommentsTitle")
        self.comments_title.setProperty("ofRole", "section")
        self.page_filter = QComboBox()
        self.page_filter.addItems([tr("Todas as páginas"), tr("Página atual")])
        self.page_filter.setAccessibleName(tr("Mostrar os comentários de"))
        self.page_filter.currentIndexChanged.connect(self._apply_page_filter)
        session.current_page_changed.connect(self._apply_page_filter)
        self.comments_list = QListWidget()
        self.comments_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.comments_list.setItemDelegate(CommentDelegate(self.comments_list))
        self.comments_list.setMouseTracking(True)
        self.comments_list.setMinimumHeight(4 * ROW_HEIGHT)
        self.comments_list.itemSelectionChanged.connect(self._on_comment_selected)
        self.comment_text_edit = QPlainTextEdit()
        self.comment_text_edit.setMaximumHeight(90)
        self.comment_author_edit = QLineEdit()
        self.comment_author_edit.setPlaceholderText(tr("Autor"))
        self.update_comment_button = QPushButton(tr("Salvar alteração do comentário"))
        self.update_comment_button.clicked.connect(self._update_comment)
        self.remove_comments_button = QPushButton(tr("Remover comentários selecionados"))
        self.remove_comments_button.clicked.connect(self._remove_comments)
        self.recolor_button = QPushButton(tr("Trocar a cor dos selecionados"))
        self.recolor_button.setToolTip(tr("Aplica aos comentários selecionados a cor escolhida na barra de marcação."))
        self.recolor_button.clicked.connect(self._recolor_comments)
        move_hint = QLabel(
            tr(
                "Com Selecionar/Apagar, arraste o comentário escolhido no visualizador para movê-lo, "
                "ou o canto inferior direito dele para mudar o tamanho."
            )
        )
        move_hint.setWordWrap(True)
        annotation_state.comment_geometry_requested.connect(self._move_comment)
        import_xfdf_button = QPushButton(tr("Importar comentários (XFDF)..."))
        import_xfdf_button.clicked.connect(self._import_xfdf)
        session.path_changed.connect(self._load_comments)

        self.export_csv_picker = FilePicker(
            mode="save", file_filter="CSV (*.csv);;Excel (*.xlsx);;XFDF (*.xfdf)"
        )
        export_csv_button = QPushButton(tr("Exportar comentários"))
        export_csv_button.setToolTip(tr("Em CSV, Excel ou XFDF, conforme o tipo do arquivo de saída."))
        export_csv_button.clicked.connect(self._export_csv)

        # Comentários (as pendentes e os gravados): uma seção própria do painel, antes das
        # opções (`extra_section`, ver ui/tool_panel.py).
        self.comments_section = QWidget()
        comments = QVBoxLayout(self.comments_section)
        comments.setContentsMargins(0, 0, 0, 0)
        comments.addWidget(self.page_filter)
        comments.addWidget(self.comments_list)
        comments.addWidget(self.comment_text_edit)
        comments.addWidget(self.comment_author_edit)
        comments.addWidget(self.update_comment_button)
        comments.addWidget(self.remove_comments_button)
        comments.addWidget(self.recolor_button)
        comments.addWidget(move_hint)
        self.extra_section = (self.comments_title, self.comments_section)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addLayout(drawing_form)
        layout.addWidget(self.stamp_label)
        layout.addWidget(self.stamp_combo)
        layout.addWidget(self.new_stamp_name_edit)
        layout.addWidget(save_stamp_button)
        layout.addWidget(remove_stamp_button)
        layout.addWidget(import_xfdf_button)
        layout.addWidget(QLabel(tr("Exportar comentários existentes:")))
        layout.addWidget(self.export_csv_picker)
        layout.addWidget(export_csv_button)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(self.save_button)

        annotation_state.pending_changed.connect(self._on_pending_changed)
        self._load_comments()
        self._update_pending()

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
            self.comments_list.addItem(tr("Nenhum comentário no documento."))
            self.comments_list.item(0).setFlags(self.comments_list.item(0).flags() & ~Qt.ItemFlag.ItemIsSelectable)
        count = len(pending) + len(self._comments)
        self.comments_title.setText(tr("Comentários · {count}").format(count=count).upper())
        self.comments_list.blockSignals(False)
        self._apply_page_filter()
        self._on_comment_selected()

    def _apply_page_filter(self):
        """"Página atual": só as marcações da página que o visualizador mostra."""
        only_current = self.page_filter.currentIndex() == 1
        current = self.session.current_page()
        for row in range(self.comments_list.count()):
            view = self.comments_list.item(row).data(ROW_VIEW)
            self.comments_list.setRowHidden(row, bool(only_current and view and view[2] != current))

    def _selected_refs(self) -> list[tuple[str, int]]:
        refs = [item.data(ROW_REF) for item in self.comments_list.selectedItems()]
        return sorted(ref for ref in refs if ref)

    def _selected_comments(self) -> list[AnnotationInfo]:
        refs = self._selected_refs()
        return [self._comments[n] for kind, n in refs if kind == "saved" and n < len(self._comments)]

    def _on_comment_selected(self):
        selected = self._selected_comments()
        single = selected[0] if len(selected) == 1 else None
        self.comment_text_edit.setPlainText(single.content if single else "")
        self.comment_author_edit.setText(single.author if single else "")
        drawn = single is not None and single.kind in _DRAWN_TEXT_KINDS
        self.comment_text_edit.setReadOnly(single is None or drawn)
        self.comment_text_edit.setToolTip(
            tr("O texto deste comentário faz parte do desenho: remova-o e crie outro.") if drawn else ""
        )
        self.comment_author_edit.setEnabled(single is not None)
        self.update_comment_button.setEnabled(single is not None)
        self.remove_comments_button.setEnabled(bool(selected))
        self.recolor_button.setEnabled(bool(selected))
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

    def _update_comment(self):
        selected = self._selected_comments()
        if len(selected) != 1:
            return
        comment = selected[0]
        content = comment.content if comment.kind in _DRAWN_TEXT_KINDS else self.comment_text_edit.toPlainText()
        author = self.comment_author_edit.text().strip()
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
            tr("Remover comentários"),
            lambda source, output: RemoveAnnotations().run(source, output, items),
            message=lambda count: tr("{count} anotação(ões) removida(s), com popups e respostas.").format(
                count=count
            ),
        )

    def _recolor_comments(self):
        items = [(c.page_index, c.index) for c in self._selected_comments()]
        if not items:
            return
        color = self.annotation_state.active_color()

        def message(result):
            changed, skipped = result
            text = tr("Cor trocada em {count} comentário(s).").format(count=changed)
            if skipped:
                text += " " + tr(
                    "{count} ficou(aram) como estava(m): carimbos, textos livres e polígonos têm o desenho fixo."
                ).format(count=skipped)
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
            text = tr("{count} comentário(s) importado(s).").format(count=imported)
            if skipped:
                text += " " + tr(
                    "{count} ignorado(s): tipo não suportado, página que não existe ou dados inválidos."
                ).format(count=skipped)
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
        self.save_button.setText(tr("Gravar {count} marcações").format(count=count) if count else tr("Gravar marcações"))
        self.save_button.setEnabled(count > 0)
        self.discard_button.setEnabled(count > 0)

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
            notify_success(self, tr("Anotações"), tr("Anotações salvas com sucesso."))

        run_task(
            self,
            tr("Gravar marcações"),  # o nome do passo no Ctrl+Z
            task,
            on_success=done,
            error_message=tr("Falha ao salvar anotações: {error}"),
        )

    def _export_csv(self):
        input_path = self.session.path()
        output_path = self.export_csv_picker.path()

        if not input_path:
            notify_error(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Anotações"), tr("Escolha o arquivo de saída."))
            return

        if output_path.lower().endswith(".xfdf"):
            task = call(ExportAnnotationsXFDF().run, input_path, output_path)
        else:
            task = call(lambda *paths: (ExportAnnotationsCSV().run(*paths), 0), input_path, output_path)

        def done(result):
            count, skipped = result
            text = tr("{count} comentário(s) exportado(s) com sucesso.").format(count=count)
            if skipped:
                text += " " + tr("{count} de tipo que o XFDF daqui não leva (anexo, som...) ficou de fora.").format(
                    count=skipped
                )
            notify_success(self, tr("Anotações"), text)

        run_task(
            self,
            tr("Anotações"),
            task,
            on_success=done,
            error_message=tr("Falha ao exportar comentários: {error}"),
        )
