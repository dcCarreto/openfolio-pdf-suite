"""Completude das traduções (B30, M42).

Três redes, do mais preciso ao mais amplo:

1. Todo `tr("...")` com texto fixo na interface tem tradução cadastrada.
2. Toda mensagem do `core` que chega ao usuário tem tradução: os modelos de `Message(...)`,
   os textos fixos de erros levantados e as mensagens de andamento.
3. Com o app em inglês, nenhuma aba mostra texto que ainda pareça português (pega rótulos
   que passam por `tr(variável)`, como as listas de modos e de tamanhos de página).
"""

import ast
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui import i18n

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = i18n._EN_TRANSLATIONS

# Erros que só acontecem por erro de programação (a interface não deixa chegar lá): não
# precisam de tradução.
_INTERNAL_ERRORS = {
    "page_count deve ser maior ou igual a 1.",
    "digits deve ser pelo menos 1.",
    "pages_per_file deve ser maior ou igual a 1.",
}


def _python_files(*folders: str):
    for folder in folders:
        yield from sorted((ROOT / folder).rglob("*.py"))


def _literal(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _calls(tree, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if called == name and node.args:
                yield node


def _missing(keys) -> list[str]:
    return sorted({key for key in keys if key and key not in TRANSLATIONS})


def test_every_fixed_interface_text_has_a_translation():
    keys = []
    for path in _python_files("ui"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        keys += [_literal(call.args[0]) for call in _calls(tree, "tr")]
    assert _missing(keys) == []


def test_every_core_message_has_a_translation():
    keys = []
    for path in _python_files("core"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        keys += [_literal(call.args[0]) for call in _calls(tree, "Message")]
        for call in _calls(tree, "update"):
            if len(call.args) >= 3:
                keys.append(_literal(call.args[2]))
        for call in _calls(tree, "steps"):
            keys += [_literal(arg) for arg in call.args[2:]] + [
                _literal(keyword.value) for keyword in call.keywords if keyword.arg == "message"
            ]
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
                text = _literal(node.exc.args[0])
                if text not in _INTERNAL_ERRORS:
                    keys.append(text)
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id.endswith("_MESSAGE") for target in node.targets
            ):
                keys.append(_literal(node.value))
    assert _missing(keys) == []


def test_translations_keep_the_same_placeholders():
    def placeholders(text: str) -> set[str]:
        return set(re.findall(r"(?<!\{)\{([a-z_]+)(?::[^}]*)?\}(?!\})", text))

    wrong = {key: value for key, value in TRANSLATIONS.items() if placeholders(key) != placeholders(value)}
    assert wrong == {}


# --- Varredura da interface em inglês --------------------------------------------------

_PORTUGUESE = re.compile(
    r"[ãõçáéíóúâêôà]|\b(de|da|das|dos|para|com|não|uma|ou|em|na|ao|pelo|pela|sem)\b", re.IGNORECASE
)
# Textos que aparecem iguais nos dois idiomas.
_SAME_IN_BOTH = {"OpenFolio PDF Suite"}


def _visible_texts(widget):
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit, QPlainTextEdit, QTableWidget

    texts = []
    for child in [widget, *widget.findChildren(object)]:
        if isinstance(child, QLabel):
            texts.append(child.text())
        if isinstance(child, QAbstractButton):
            texts.append(child.text())
        if isinstance(child, QGroupBox):
            texts.append(child.title())
        if isinstance(child, (QLineEdit, QPlainTextEdit)):
            texts.append(child.placeholderText())
        if isinstance(child, QComboBox):
            texts += [child.itemText(i) for i in range(child.count())]
        if isinstance(child, QTableWidget):
            texts += [
                child.horizontalHeaderItem(i).text()
                for i in range(child.columnCount())
                if child.horizontalHeaderItem(i) is not None
            ]
        if hasattr(child, "toolTip"):
            texts.append(child.toolTip())
    return [text for text in texts if text]


def _looks_portuguese(text: str) -> bool:
    plain = re.sub(r"<[^>]+>|\S+\.\S+", "", text)  # sem tags, endereços e nomes de arquivo
    return text not in _SAME_IN_BOTH and bool(_PORTUGUESE.search(plain))


@pytest.fixture
def english():
    i18n.set_language(i18n.EN_US)
    yield
    i18n.set_language(i18n.PT_BR)


_SAME_TEXT = re.compile(r"^PDF/A-\d$")


def _collect_tab_texts():
    from PySide6.QtWidgets import QApplication

    from ui.main_window import _SECTIONS, MainWindow

    QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        tabs = {_SECTIONS[row][4]: _visible_texts(window._ensure_page(row)) for row in range(len(_SECTIONS))}
        tabs["sidebar"] = [window.sidebar.item(row).text() for row in range(window.sidebar.count())]
    finally:
        window.close()
    return tabs


def test_no_text_stays_the_same_after_switching_to_english():
    # Pega o que a varredura por "cara de português" deixa passar ("Preto", "Cinza") e o
    # inverso: texto fixo em inglês que aparece também com o app em português.
    portuguese = _collect_tab_texts()
    i18n.set_language(i18n.EN_US)
    try:
        english = _collect_tab_texts()
    finally:
        i18n.set_language(i18n.PT_BR)
    unchanged = {}
    for tab, texts in portuguese.items():
        same = {
            pt
            for pt, en in zip(texts, english[tab])
            if pt == en and re.search(r"[A-Za-zÀ-ú]{3,}", pt) and TRANSLATIONS.get(pt) != pt and not _SAME_TEXT.match(pt)
        }
        if same:
            unchanged[tab] = sorted(same)
    assert unchanged == {}


def test_no_tab_shows_portuguese_in_english(english):
    from PySide6.QtWidgets import QApplication

    from ui.main_window import _SECTIONS, MainWindow

    QApplication.instance() or QApplication([])
    window = MainWindow()
    leftovers = {}
    try:
        for row in range(len(_SECTIONS)):
            page = window._ensure_page(row)
            found = sorted({text for text in _visible_texts(page) if _looks_portuguese(text)})
            if found:
                leftovers[_SECTIONS[row][4]] = found
        sidebar = [window.sidebar.item(row).text() for row in range(window.sidebar.count())]
        leftovers.update({"sidebar": [t for t in sidebar if _looks_portuguese(t)]} if any(map(_looks_portuguese, sidebar)) else {})
    finally:
        window.close()
    assert leftovers == {}
