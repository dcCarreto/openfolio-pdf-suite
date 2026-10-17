"""Operações fora da thread da interface, cancelamento, log e janela que não perde o estado."""

import logging
import os
import subprocess
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QListWidget, QMessageBox

from core.progress import OperationCancelled, Progress
from core.redaction import RedactDocument, RedactionRect
from ui import i18n
from ui.tasks import call, call_with_progress, run_task, task_manager, wait_for_tasks


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _reset_language():
    i18n.set_language(i18n.PT_BR)
    yield
    wait_for_tasks()
    i18n.set_language(i18n.PT_BR)


# -- Progress -------------------------------------------------------------------------


def test_progress_steps_report_and_stop_when_cancelled():
    reports = []
    progress = Progress(callback=lambda done, total, message: reports.append((done, total, message)))

    seen = []
    with pytest.raises(OperationCancelled):
        for item in progress.steps(["a", "b", "c"], message="Etapa"):
            seen.append(item)
            if item == "b":
                progress.cancel()

    assert seen == ["a", "b"]
    assert reports[:2] == [(0, 3, "Etapa"), (1, 3, "Etapa")]


def test_cancelled_redaction_writes_nothing(make_text_pdf, tmp_path):
    source = make_text_pdf("doc.pdf", [(80, 700, "segredo")])
    output = tmp_path / "out.pdf"
    progress = Progress()
    progress.cancel()

    with pytest.raises(OperationCancelled):
        RedactDocument().run(
            str(source), str(output), [RedactionRect(0, 70, 690, 200, 720)], progress=progress
        )

    assert not output.exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".openfolio-")]


# -- TaskManager / run_task ---------------------------------------------------------


def test_task_runs_outside_the_interface_thread_and_returns_the_result():
    _app()
    main_thread = threading.get_ident()
    results = []

    started = run_task(None, "Teste", lambda progress: threading.get_ident(), on_success=results.append)
    assert started
    assert wait_for_tasks()

    assert results and results[0] != main_thread


def test_only_one_task_runs_at_a_time(monkeypatch):
    _app()
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    release = threading.Event()

    assert run_task(None, "Lenta", lambda progress: release.wait(5))
    assert not run_task(None, "Outra", lambda progress: None)
    assert "Lenta" in messages[0]

    release.set()
    assert wait_for_tasks()


def test_cancel_stops_the_task_without_an_error_dialog(monkeypatch):
    _app()
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args))
    outcomes = []
    task_manager().finished.connect(outcomes.append)

    def slow(progress):
        for _ in progress.steps(range(500)):
            time.sleep(0.01)

    try:
        run_task(None, "Lenta", slow)
        time.sleep(0.05)
        task_manager().cancel()
        assert wait_for_tasks()
    finally:
        task_manager().finished.disconnect(outcomes.append)

    assert outcomes == ["cancelled"]
    assert errors == []


def test_task_error_is_shown_with_the_page_message_and_logged(monkeypatch, caplog):
    _app()
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text: shown.append((title, text)))
    caplog.set_level(logging.INFO)

    def broken(progress):
        raise RuntimeError("deu errado")

    run_task(None, "Comprimir", broken, error_message="Falha ao comprimir: {error}")
    wait_for_tasks()

    assert shown == [("Comprimir", "Falha ao comprimir: deu errado")]
    record = next(r for r in caplog.records if r.name == "ui.tasks" and r.levelno == logging.ERROR)
    assert record.exc_info is not None  # erro inesperado: rastro completo no log


def test_call_helpers_evaluate_arguments_right_away():
    values = {"x": 1}
    task = call(lambda value: value, values["x"])
    values["x"] = 2
    assert task(Progress()) == 1

    received = []
    with_progress = call_with_progress(lambda value, progress: received.append((value, progress)), 3)
    marker = Progress()
    with_progress(marker)
    assert received == [(3, marker)]


# -- Janela principal -----------------------------------------------------------------


def test_window_fits_a_1280x720_screen():
    # Largura mínima era 1356 px (barra lateral e painel com largura fixa).
    _app()
    from ui.main_window import MainWindow

    window = MainWindow()
    try:
        assert window.minimumSizeHint().width() <= 1280
        window.resize(1280, 720)
        window.show()
        QApplication.processEvents()
        assert window.width() <= 1280
        assert all(size > 0 for size in window.splitter.sizes())
    finally:
        window.close()


def test_tool_panel_is_locked_while_a_task_runs():
    _app()
    from ui.main_window import MainWindow

    window = MainWindow()
    release = threading.Event()
    try:
        run_task(window, "Lenta", lambda progress: release.wait(5))
        QApplication.processEvents()
        assert not window.stack.isEnabled()
        assert window.task_status.isVisibleTo(window)
        release.set()
        wait_for_tasks()
        assert window.stack.isEnabled()
    finally:
        release.set()
        window.close()


def test_language_change_keeps_what_the_user_typed(tmp_path):
    # Antes, trocar de idioma reconstruía a UI e apagava o que estava preenchido.
    _app()
    from ui.main_window import MainWindow

    window = MainWindow()
    try:
        watermark_row = window._row_of["WatermarkPage"]
        merge_row = window._row_of["MergePage"]
        window.sidebar.setCurrentRow(watermark_row)
        watermark = window.page(watermark_row)
        watermark.text_edit.setText("CONFIDENCIAL")
        watermark.font_size_spin.setValue(72)
        watermark.output_picker.restore((str(tmp_path / "saida.pdf"), None))
        merge = window.page(merge_row)
        merge.file_list_editor.list_widget.addItems(["a.pdf", "b.pdf"])

        i18n.set_language(i18n.EN_US)

        new_watermark = window.page(watermark_row)
        assert new_watermark is not watermark
        assert new_watermark.text_edit.text() == "CONFIDENCIAL"
        assert new_watermark.font_size_spin.value() == 72
        assert new_watermark.output_picker.path() == str(tmp_path / "saida.pdf")
        assert window.page(merge_row).file_list_editor.paths() == ["a.pdf", "b.pdf"]
        assert window.sidebar.currentRow() == watermark_row
        sidebar = window.findChild(QListWidget, "sidebar")
        assert sidebar.item(merge_row).text() == "Merge"
    finally:
        window.close()


def test_language_change_keeps_the_open_document_and_viewer_state(make_text_pdf):
    _app()
    from ui.main_window import MainWindow

    path = make_text_pdf("doc.pdf", [(80, 700, "um")] )
    window = MainWindow()
    try:
        window.session.open(str(path))
        viewer = window.viewer
        viewer._zoom_in()
        scale = viewer._scale

        i18n.set_language(i18n.EN_US)

        assert window.viewer is viewer
        assert viewer._scale == scale
        assert viewer._document is not None
        assert viewer.page_indicator.toolTip().startswith("Page 1 of 1")
    finally:
        window.close()


def test_every_section_points_to_an_existing_page_class():
    from importlib import import_module

    from ui.main_window import _SECTIONS

    for _icon, _title, _subtitle, module_name, class_name in _SECTIONS:
        assert hasattr(import_module(module_name), class_name), (module_name, class_name)


def test_opening_the_window_does_not_import_heavy_tool_libraries():
    # pyhanko (assinatura) e pytesseract (OCR) só carregam quando a aba é aberta.
    code = (
        "import os, sys; os.environ['QT_QPA_PLATFORM'] = 'offscreen';"
        "from PySide6.QtWidgets import QApplication; app = QApplication([]);"
        "from ui.main_window import MainWindow; MainWindow();"
        "print(sorted(m for m in ('pyhanko', 'pytesseract', 'docx', 'openpyxl', 'pptx') if m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=os.getcwd(), timeout=120
    )
    assert result.stdout.strip().splitlines()[-1] == "[]", result.stderr


# -- Log e exceções não tratadas -----------------------------------------------------------


def test_setup_logging_writes_to_a_file(tmp_path):
    from ui import diagnostics

    root = logging.getLogger()
    before = list(root.handlers)
    try:
        path = diagnostics.setup_logging(tmp_path / "logs")
        logging.getLogger("openfolio.teste").warning("mensagem de teste")
        for handler in root.handlers:
            handler.flush()
        assert path is not None and "mensagem de teste" in path.read_text(encoding="utf-8")
    finally:
        for handler in root.handlers[:]:
            if handler not in before:
                root.removeHandler(handler)
                handler.close()


def test_unhandled_exceptions_are_logged_and_reported(monkeypatch, caplog):
    _app()
    from ui import diagnostics

    reported = []
    monkeypatch.setattr(diagnostics._ErrorReporter, "_show", lambda self, summary, details: reported.append(summary))
    previous_hooks = (sys.excepthook, threading.excepthook)
    caplog.set_level(logging.INFO)
    try:
        diagnostics.install_exception_hooks()
        diagnostics._reporter.report.disconnect()
        diagnostics._reporter.report.connect(lambda summary, details: reported.append(summary))

        thread = threading.Thread(target=lambda: 1 / 0, name="trabalho")
        thread.start()
        thread.join()
        QApplication.processEvents()
    finally:
        sys.excepthook, threading.excepthook = previous_hooks

    assert any("ZeroDivisionError" in summary for summary in reported)
    record = next(r for r in caplog.records if r.levelno == logging.CRITICAL)
    assert "trabalho" in record.getMessage()
