"""Ponto de entrada da aplicação."""

import importlib
import logging
import sys
import threading

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication

from core.version import APP_VERSION
from ui.app_events import FileOpenFilter, pdf_paths_from_arguments
from ui.diagnostics import install_exception_hooks, setup_logging
from ui.instances import AppWindows, InstanceServer, send_to_running_instance
from ui.main_window import MainWindow
from ui.preferences import Preferences
from ui.theme import apply_theme


# Bibliotecas que só o documento aberto usa. A janela abre sem elas (ver `_is_document` em
# ui/main_window.py); carregadas numa thread logo depois, o primeiro PDF não espera por elas.
# Só bibliotecas de fora: nenhuma importa o app de volta, então a thread não disputa com a da
# interface um módulo pela metade.
_WARM_UP = ("pypdf", "reportlab.pdfgen.canvas", "PIL.Image", "PIL.ImageQt")


def _warm_up_libraries() -> None:
    def run():
        for name in _WARM_UP:
            try:
                importlib.import_module(name)
            except Exception:  # noqa: BLE001 — quem precisar dela importa de novo e vê o erro
                logging.getLogger("openfolio").debug("Pré-carga de %s falhou", name, exc_info=True)

    threading.Thread(target=run, name="openfolio-warm-up", daemon=True).start()


def main():
    app = QApplication(sys.argv)
    # Nomes usados pela pasta de dados (log) e pelas preferências (tamanho da janela).
    app.setOrganizationName("OpenFolio")
    app.setApplicationName("OpenFolio PDF Suite")
    app.setApplicationVersion(APP_VERSION)

    # "Abrir com" / duplo clique num PDF: o arquivo chega como argumento (Windows, Linux)
    # ou como evento FileOpen (macOS). Com o app já aberto, é ele que abre.
    paths = pdf_paths_from_arguments(sys.argv[1:])
    if send_to_running_instance(paths):
        return

    log_file = setup_logging()
    install_exception_hooks()
    # O identificador da atualização (a data) não aparece na interface; no log, ajuda o suporte.
    logging.getLogger("openfolio").info("OpenFolio PDF Suite iniciado (atualização %s, log: %s)", APP_VERSION, log_file)

    settings = QSettings()
    preferences = Preferences(settings)
    apply_theme(app, preferences.theme())

    def make_window():
        window = MainWindow(settings=settings)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        return window

    windows = AppWindows(make_window)
    windows.open([])
    windows.windows()[0].offer_app_menu()
    if preferences.check_updates_on_start() and preferences.update_check_due():
        windows.windows()[0].check_for_updates(manual=False)

    file_open_filter = FileOpenFilter(lambda path: windows.open([path]))
    app.installEventFilter(file_open_filter)
    _server = InstanceServer(windows.open)  # vive até o app fechar
    windows.open(paths)
    QTimer.singleShot(300, _warm_up_libraries)  # depois da primeira pintura da janela
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
