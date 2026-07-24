"""Aba de marcadores (sumário/outline) de PDFs."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.bookmarks import AddBookmarks
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class BookmarksPage(QWidget):
    """Permite montar um sumário (marcadores de navegação) e aplicá-lo a um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(mode="save")

        self.bookmark_list = QListWidget()

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(tr("Título do marcador"))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, 9999)

        add_button = QPushButton(tr("Adicionar"))
        add_button.clicked.connect(self._add_bookmark)
        remove_button = QPushButton(tr("Remover selecionado"))
        remove_button.clicked.connect(self._remove_selected)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel(tr("Página (0 = primeira):")))
        page_row.addWidget(self.page_spin)
        page_row.addWidget(add_button)

        add_row = QVBoxLayout()
        add_row.addWidget(self.title_edit)
        add_row.addLayout(page_row)

        save_button = QPushButton(tr("Salvar"))
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Marcadores:")))
        layout.addWidget(self.bookmark_list)
        layout.addLayout(add_row)
        layout.addWidget(remove_button)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(save_button)

    def _add_bookmark(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, tr("Marcadores"), tr("Digite um título para o marcador."))
            return

        page_number = self.page_spin.value()
        item = QListWidgetItem(tr("{title} — página {page}").format(title=title, page=page_number))
        item.setData(Qt.ItemDataRole.UserRole, (title, page_number))
        self.bookmark_list.addItem(item)
        self.title_edit.clear()

    def _remove_selected(self):
        for item in self.bookmark_list.selectedItems():
            self.bookmark_list.takeItem(self.bookmark_list.row(item))

    def _save(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Marcadores"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Marcadores"), tr("Escolha o arquivo de saída."))
            return

        bookmarks = [
            self.bookmark_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.bookmark_list.count())
        ]
        if not bookmarks:
            QMessageBox.warning(self, tr("Marcadores"), tr("Adicione pelo menos um marcador."))
            return

        try:
            AddBookmarks().run(input_path, output_path, bookmarks=bookmarks)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Marcadores"), tr("Falha ao salvar marcadores: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Marcadores"), tr("Marcadores salvos com sucesso."))
