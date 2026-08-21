"""Aba de anexos embutidos: listar, adicionar, remover e extrair."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.attachments import AddAttachment, ExtractAttachments, ListAttachments, RemoveAttachment
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    return f"{size / 1024:.1f} KB"


class AttachmentsPage(QWidget):
    """Permite listar, adicionar, remover e extrair os anexos embutidos de um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [tr("Listar"), tr("Adicionar"), tr("Remover"), tr("Extrair todos")]
        )
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_list_panel())
        self.stack.addWidget(self._build_add_panel())
        self.stack.addWidget(self._build_remove_panel())
        self.stack.addWidget(self._build_extract_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_list_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        list_button = QPushButton(tr("Listar anexos"))
        list_button.clicked.connect(self._list_attachments)
        self.attachments_list = QListWidget()

        layout.addWidget(list_button)
        layout.addWidget(self.attachments_list)
        return widget

    def _build_add_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.add_file_picker = FilePicker(mode="open")
        self.add_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="com_anexo"
        )
        add_button = QPushButton(tr("Adicionar anexo"))
        add_button.clicked.connect(self._add_attachment)

        layout.addWidget(QLabel(tr("Arquivo a anexar:")))
        layout.addWidget(self.add_file_picker)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.add_output_picker)
        layout.addWidget(add_button)
        return widget

    def _build_remove_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(tr('Use "Listar" para descobrir o nome exato do anexo a remover.'))
        note.setWordWrap(True)

        self.remove_name_edit = QLineEdit()
        self.remove_name_edit.setPlaceholderText(tr("Nome do anexo, ex: notas.txt"))
        self.remove_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="sem_anexo"
        )
        remove_button = QPushButton(tr("Remover anexo"))
        remove_button.clicked.connect(self._remove_attachment)

        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Nome do anexo:")))
        layout.addWidget(self.remove_name_edit)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.remove_output_picker)
        layout.addWidget(remove_button)
        return widget

    def _build_extract_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.extract_output_picker = FilePicker(mode="directory")
        extract_button = QPushButton(tr("Extrair anexos"))
        extract_button.clicked.connect(self._extract_attachments)

        layout.addWidget(QLabel(tr("Pasta de saída:")))
        layout.addWidget(self.extract_output_picker)
        layout.addWidget(extract_button)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _list_attachments(self):
        input_path = self.session.path()
        self.attachments_list.clear()
        if not input_path:
            QMessageBox.warning(self, tr("Anexos"), tr("Abra um PDF para começar."))
            return

        try:
            attachments = ListAttachments().run(input_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anexos"), tr("Falha ao listar anexos: {error}").format(error=exc)
            )
            return

        if not attachments:
            self.attachments_list.addItem(tr("Nenhum anexo embutido encontrado."))
            return
        for attachment in attachments:
            self.attachments_list.addItem(f"{attachment.name} — {_format_size(attachment.size)}")

    def _add_attachment(self):
        input_path = self.session.path()
        attachment_path = self.add_file_picker.path()
        output_path = self.add_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Anexos"), tr("Abra um PDF para começar."))
            return
        if not attachment_path:
            QMessageBox.warning(self, tr("Anexos"), tr("Escolha o arquivo a anexar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Anexos"), tr("Escolha o arquivo de saída."))
            return

        try:
            AddAttachment().run(input_path, output_path, attachment_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anexos"), tr("Falha ao adicionar anexo: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Anexos"), tr("Anexo adicionado com sucesso."))

    def _remove_attachment(self):
        input_path = self.session.path()
        output_path = self.remove_output_picker.path()
        name = self.remove_name_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, tr("Anexos"), tr("Abra um PDF para começar."))
            return
        if not name:
            QMessageBox.warning(self, tr("Anexos"), tr("Digite o nome do anexo a remover."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Anexos"), tr("Escolha o arquivo de saída."))
            return

        try:
            RemoveAttachment().run(input_path, output_path, name=name)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anexos"), tr("Falha ao remover anexo: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Anexos"), tr("Anexo removido com sucesso."))

    def _extract_attachments(self):
        input_path = self.session.path()
        output_dir = self.extract_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Anexos"), tr("Abra um PDF para começar."))
            return
        if not output_dir:
            QMessageBox.warning(self, tr("Anexos"), tr("Escolha a pasta de saída."))
            return

        try:
            output_paths = ExtractAttachments().run(input_path, output_dir)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anexos"), tr("Falha ao extrair anexos: {error}").format(error=exc)
            )
            return

        QMessageBox.information(
            self,
            tr("Anexos"),
            tr("{count} anexo(s) extraído(s) com sucesso.").format(count=len(output_paths)),
        )
