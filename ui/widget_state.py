"""Cópia do que o usuário preencheu numa aba para outra instância da mesma aba.

Trocar de idioma reconstrói as abas (os textos são traduzidos na construção). Antes, isso
apagava tudo o que tinha sido digitado ou escolhido: o texto da marca d'água, a lista de
arquivos a mesclar, os marcadores montados, os arquivos de saída escolhidos.

Como a aba nova é montada pelo mesmo código, a árvore de widgets tem a mesma forma: os
widgets com estado são pareados pela ordem em que aparecem e pelo tipo. Widgets compostos
(caixas de número, combos, seletores de arquivo, listas, tabelas) são tratados como uma
unidade, sem descer nos widgets internos deles.
"""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QWidget,
)

from ui.widgets.file_picker import FilePicker

# Ordem importa: subclasses antes das classes-base.
_STATEFUL_TYPES = (
    FilePicker,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QTableWidget,
    QListWidget,
    QAbstractButton,
)
# Widgets cujo conteúdo interno não deve ser visitado.
_OPAQUE_TYPES = (FilePicker, QComboBox, QAbstractSpinBox, QTableWidget, QListWidget)
_ROLES = (Qt.ItemDataRole.UserRole, Qt.ItemDataRole.CheckStateRole)


def _stateful_widgets(root: QWidget) -> list[QWidget]:
    found: list[QWidget] = []

    def visit(widget: QWidget):
        for child in widget.children():
            if not isinstance(child, QWidget):
                continue
            if isinstance(child, _STATEFUL_TYPES):
                if not isinstance(child, QAbstractButton) or child.isCheckable():
                    found.append(child)
            if not isinstance(child, _OPAQUE_TYPES):
                visit(child)

    visit(root)
    return found


def _kind(widget: QWidget) -> type:
    return next(kind for kind in _STATEFUL_TYPES if isinstance(widget, kind))


def _list_item_state(item: QListWidgetItem) -> dict[str, Any]:
    return {
        "text": item.text(),
        "data": {int(role.value): item.data(role) for role in _ROLES if item.data(role) is not None},
        "icon": item.icon(),
        "flags": item.flags(),
    }


def _capture_one(widget: QWidget) -> Any:
    if isinstance(widget, FilePicker):
        return widget.snapshot()
    if isinstance(widget, QComboBox):
        return widget.currentText() if widget.isEditable() else widget.currentIndex()
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.value()
    if isinstance(widget, QLineEdit):
        return None if widget.isReadOnly() else widget.text()
    if isinstance(widget, (QPlainTextEdit, QTextEdit)):
        return None if widget.isReadOnly() else widget.toPlainText()
    if isinstance(widget, QTableWidget):
        cells = [
            [widget.item(row, column).text() if widget.item(row, column) else None for column in range(widget.columnCount())]
            for row in range(widget.rowCount())
        ]
        return cells
    if isinstance(widget, QListWidget):
        return [_list_item_state(widget.item(row)) for row in range(widget.count())]
    if isinstance(widget, QAbstractButton):
        return widget.isChecked()
    return None


def _restore_one(widget: QWidget, state: Any) -> None:
    if state is None:
        return
    if isinstance(widget, FilePicker):
        widget.restore(state)
    elif isinstance(widget, QComboBox):
        if widget.isEditable():
            widget.setCurrentText(state)
        elif 0 <= state < widget.count():
            widget.setCurrentIndex(state)
    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.setValue(state)
    elif isinstance(widget, QLineEdit):
        widget.setText(state)
    elif isinstance(widget, (QPlainTextEdit, QTextEdit)):
        widget.setPlainText(state)
    elif isinstance(widget, QTableWidget):
        widget.setRowCount(len(state))
        for row, cells in enumerate(state):
            for column, text in enumerate(cells[: widget.columnCount()]):
                if text is not None:
                    widget.setItem(row, column, QTableWidgetItem(text))
    elif isinstance(widget, QListWidget):
        widget.clear()
        for item_state in state:
            item = QListWidgetItem(item_state["icon"], item_state["text"])
            item.setFlags(item_state["flags"])
            for role, value in item_state["data"].items():
                item.setData(Qt.ItemDataRole(role), value)
            widget.addItem(item)
    elif isinstance(widget, QAbstractButton):
        widget.setChecked(state)


def capture_state(root: QWidget) -> list[tuple[type, Any]]:
    """O estado de cada widget preenchível de `root`, na ordem da árvore."""
    return [(_kind(widget), _capture_one(widget)) for widget in _stateful_widgets(root)]


def restore_state(root: QWidget, states: list[tuple[type, Any]]) -> None:
    """Aplica em `root` o estado capturado de outra instância da mesma aba.

    Combos e botões vão primeiro: eles trocam o painel visível e podem preencher campos
    (o tamanho de página preenche largura e altura, por exemplo); o que o usuário digitou
    vem depois e prevalece.
    """
    widgets = _stateful_widgets(root)
    if len(widgets) != len(states):
        return  # a aba mudou de forma (não deveria acontecer); melhor não arriscar
    pairs = [(widget, state) for widget, (kind, state) in zip(widgets, states) if isinstance(widget, kind)]
    selectors = [pair for pair in pairs if isinstance(pair[0], (QComboBox, QAbstractButton))]
    others = [pair for pair in pairs if not isinstance(pair[0], (QComboBox, QAbstractButton))]
    for widget, state in [*selectors, *others]:
        try:
            _restore_one(widget, state)
        except (TypeError, ValueError, RuntimeError):
            continue  # um campo que não volta não deve impedir a troca de idioma
