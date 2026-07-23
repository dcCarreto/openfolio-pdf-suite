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
from ui.widgets.file_picker import FilePicker


class BookmarksPage(QWidget):
    """Permite montar um sumário (marcadores de navegação) e aplicá-lo a um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="save")

        self.bookmark_list = QListWidget()

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Título do marcador")
        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, 9999)

        add_button = QPushButton("Adicionar")
        add_button.clicked.connect(self._add_bookmark)
        remove_button = QPushButton("Remover selecionado")
        remove_button.clicked.connect(self._remove_selected)

        add_row = QHBoxLayout()
        add_row.addWidget(self.title_edit)
        add_row.addWidget(QLabel("Página (0 = primeira):"))
        add_row.addWidget(self.page_spin)
        add_row.addWidget(add_button)

        save_button = QPushButton("Salvar")
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel("Marcadores:"))
        layout.addWidget(self.bookmark_list)
        layout.addLayout(add_row)
        layout.addWidget(remove_button)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(save_button)

    def _add_bookmark(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Marcadores", "Digite um título para o marcador.")
            return

        page_number = self.page_spin.value()
        item = QListWidgetItem(f"{title} — página {page_number}")
        item.setData(Qt.ItemDataRole.UserRole, (title, page_number))
        self.bookmark_list.addItem(item)
        self.title_edit.clear()

    def _remove_selected(self):
        for item in self.bookmark_list.selectedItems():
            self.bookmark_list.takeItem(self.bookmark_list.row(item))

    def _save(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Marcadores", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Marcadores", "Escolha o arquivo de saída.")
            return

        bookmarks = [
            self.bookmark_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.bookmark_list.count())
        ]
        if not bookmarks:
            QMessageBox.warning(self, "Marcadores", "Adicione pelo menos um marcador.")
            return

        try:
            AddBookmarks().run(input_path, output_path, bookmarks=bookmarks)
        except Exception as exc:
            QMessageBox.critical(self, "Marcadores", f"Falha ao salvar marcadores: {exc}")
            return

        QMessageBox.information(self, "Marcadores", "Marcadores salvos com sucesso.")
