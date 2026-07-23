"""Aba de proteção por senha de PDFs."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.protect import ProtectPDF, UnlockPDF
from ui.widgets.file_picker import FilePicker


class ProtectPage(QWidget):
    """Permite proteger um PDF com senha ou remover a senha de um PDF protegido."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Proteger com senha", "Remover senha"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_panel("Proteger"))
        self.stack.addWidget(self._build_panel("Remover"))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Operação:"))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_panel(self, kind: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        input_picker = FilePicker(mode="open")
        output_picker = FilePicker(mode="save")
        password_edit = QLineEdit()
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_edit.setPlaceholderText("Senha")

        button_label = "Proteger" if kind == "Proteger" else "Remover senha"
        apply_button = QPushButton(button_label)

        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(input_picker)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(output_picker)
        layout.addWidget(QLabel("Senha:"))
        layout.addWidget(password_edit)
        layout.addWidget(apply_button)

        if kind == "Proteger":
            self.protect_input_picker = input_picker
            self.protect_output_picker = output_picker
            self.protect_password_edit = password_edit
            apply_button.clicked.connect(self._protect)
        else:
            self.unlock_input_picker = input_picker
            self.unlock_output_picker = output_picker
            self.unlock_password_edit = password_edit
            apply_button.clicked.connect(self._unlock)

        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _protect(self):
        input_path = self.protect_input_picker.path()
        output_path = self.protect_output_picker.path()
        password = self.protect_password_edit.text()

        if not input_path:
            QMessageBox.warning(self, "Proteger", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Proteger", "Escolha o arquivo de saída.")
            return
        if not password:
            QMessageBox.warning(self, "Proteger", "Digite uma senha.")
            return

        try:
            ProtectPDF().run(input_path, output_path, password=password)
        except Exception as exc:
            QMessageBox.critical(self, "Proteger", f"Falha ao proteger o PDF: {exc}")
            return

        QMessageBox.information(self, "Proteger", "PDF protegido com sucesso.")

    def _unlock(self):
        input_path = self.unlock_input_picker.path()
        output_path = self.unlock_output_picker.path()
        password = self.unlock_password_edit.text()

        if not input_path:
            QMessageBox.warning(self, "Remover senha", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Remover senha", "Escolha o arquivo de saída.")
            return
        if not password:
            QMessageBox.warning(self, "Remover senha", "Digite a senha atual do PDF.")
            return

        try:
            UnlockPDF().run(input_path, output_path, password=password)
        except Exception as exc:
            QMessageBox.critical(self, "Remover senha", f"Falha ao remover a senha: {exc}")
            return

        QMessageBox.information(self, "Remover senha", "Senha removida com sucesso.")
