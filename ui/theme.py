"""Temas visuais "Noturno": escuro (o padrão), claro ou o do sistema.

Tudo sai de `TOKENS`: o stylesheet (`build_qss`), a QPalette dos widgets nativos e a cor dos
ícones desenhados pelo app (`icon_color`, usada por `ui/icon_utils.py`). A fonte é a Inter
(SIL OFL 1.1), embutida em assets/fonts/; sem ela, fica a do sistema.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QDir, QPointF, Qt, QTemporaryDir
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

DARK = "dark"
LIGHT = "light"
SYSTEM = "system"
THEMES = (DARK, LIGHT, SYSTEM)

TOKENS = {
    DARK: {
        "bg": "#111821",  # janela, barras, coluna rápida
        "canvas": "#0b1017",  # fundo do visualizador: a página é o único ponto claro
        "panel": "#18202b",  # painel da ferramenta, cartões, popovers
        "raised": "#212b38",  # aba ativa, botão secundário, cartão de entrada
        "field": "#0e141c",  # campos de entrada
        "hover": "#283342",
        "pressed": "#303c4d",
        "border": "#253040",  # divisões entre regiões (uso mínimo)
        "border_strong": "#3e4b5e",  # contorno de campo, tracejado, rádio, caixa de seleção
        "text": "#e8eef5",
        "text2": "#aab6c6",
        "text3": "#8593a6",
        "accent": "#5aa6ee",  # o azul do ícone: ícone ativo, indicadores, progresso
        "accent_strong": "#a8ccf2",  # texto na cor do acento
        "accent_fill": "#172c44",  # fundo do selecionado
        "accent_line": "#2f5f93",  # borda do selecionado
        "primary": "#2a74c2",  # fundo do botão principal; mais claro, o branco sai do AA
        "primary_hover": "#2468b0",
        "on_primary": "#ffffff",
        "focus": "#a8ccf2",  # borda de foco de 2 px
        "success": "#5ccb9c",
        "success_fill": "#15302a",
        "warning": "#e8bb5e",
        "warning_fill": "#352c17",
        "danger": "#f28585",
        "danger_fill": "#3a1f26",
        "scrim": "rgba(4, 8, 14, 0.55)",
        "shadow": "rgba(0, 0, 0, 0.45)",
    },
    LIGHT: {
        "bg": "#eaeff5",
        "canvas": "#dbe2eb",
        "panel": "#ffffff",
        "raised": "#f1f4f8",
        "field": "#ffffff",
        "hover": "#e3e9f0",
        "pressed": "#d5dde8",
        "border": "#d9e0e9",
        "border_strong": "#a9b5c4",
        "text": "#141b25",
        "text2": "#445163",
        "text3": "#5a687b",
        "accent": "#2a74c2",
        "accent_strong": "#1d5a9c",
        "accent_fill": "#e6f0fb",
        "accent_line": "#a8ccf2",
        "primary": "#2a74c2",
        "primary_hover": "#2366ab",
        "on_primary": "#ffffff",
        "focus": "#2a74c2",
        "success": "#1d7a4e",
        "success_fill": "#e3f4eb",
        "warning": "#8a5a00",
        "warning_fill": "#fbf0d9",
        "danger": "#b3363b",
        "danger_fill": "#fbe6e6",
        "scrim": "rgba(14, 22, 34, 0.35)",
        "shadow": "rgba(20, 34, 56, 0.18)",
    },
}

# Cores das marcações sobre a página: iguais nos dois temas, fora dos tokens.
MARK_COLORS = {"highlight": "#ffe45c", "note": "#f5b942", "shape": "#e0473c", "pending": "#b07800"}

_current = DARK

FONT_FAMILY = "Inter"
FONT_PIXEL_SIZE = 13
_FONT_STACK = '"Inter", "Segoe UI", "Cantarell", "SF Pro Text", "Helvetica Neue", sans-serif'
_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_fonts_loaded = False

_images: QTemporaryDir | None = None  # as setas e o "✓" que o QSS desenha, um PNG por tema


def tokens(theme: str | None = None) -> dict:
    """Os tokens do tema aplicado (ou de `theme`, DARK ou LIGHT)."""
    return TOKENS[theme or _current]


def color(key: str) -> QColor:
    """A cor de um token do tema aplicado, também as escritas como "rgba(r, g, b, a)"."""
    value = TOKENS[_current][key]
    if value.startswith("rgba("):
        red, green, blue, alpha = (part.strip() for part in value[5:-1].split(","))
        return QColor(int(red), int(green), int(blue), round(float(alpha) * 255))
    return QColor(value)


def floating_shadow(parent: QWidget, modal: bool = False) -> QGraphicsDropShadowEffect:
    """Elevação 1 das superfícies flutuantes (gaveta, barra de marcação, popovers) ou, com
    `modal`, a 2 da paleta e dos diálogos, que têm o véu por trás."""
    shadow = QGraphicsDropShadowEffect(parent)
    shadow.setBlurRadius(48 if modal else 24)
    shadow.setOffset(0, 16 if modal else 8)
    shadow.setColor(color("shadow"))
    return shadow


def load_fonts() -> bool:
    """Registra a Inter embutida (uma vez). False se não deu: o QSS cai na fonte do sistema."""
    global _fonts_loaded
    if not _fonts_loaded:
        _fonts_loaded = True
        for path in sorted(_FONTS_DIR.glob("Inter-*.ttf")):
            QFontDatabase.addApplicationFont(str(path))
    return FONT_FAMILY in QFontDatabase.families()


def icon_color(mode: QIcon.Mode, state: QIcon.State = QIcon.State.Off) -> QColor:
    """A cor do traço de um ícone do app em cada estado: normal em texto secundário, sob o
    mouse em texto, marcado/selecionado no acento e desabilitado esmaecido."""
    t = TOKENS[_current]
    if mode == QIcon.Mode.Disabled:
        color = QColor(t["text2"])
        color.setAlphaF(0.45)
        return color
    if mode == QIcon.Mode.Selected or state == QIcon.State.On:
        return QColor(t["accent"])
    return QColor(t["text"] if mode == QIcon.Mode.Active else t["text2"])


def _draw_image(path: str, size: int, color: str, points: list[tuple[float, float]], width: float) -> None:
    for scale, suffix in ((1, ""), (2, "@2x")):
        image = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        pen = QPen(QColor(color), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline([QPointF(x, y) for x, y in points])
        painter.end()
        image.save(path.replace(".png", f"{suffix}.png"))


def _ensure_images() -> None:
    """Grava os PNGs que o QSS usa (o QSS só desenha imagem de arquivo) e registra a pasta
    como "of:", para o stylesheet apontar `url(of:caret-down-dark.png)`."""
    global _images
    if _images is not None:
        return
    _images = QTemporaryDir()
    folder = _images.path()
    for key, t in TOKENS.items():
        _draw_image(f"{folder}/caret-down-{key}.png", 12, t["text2"], [(3, 4.5), (6, 7.5), (9, 4.5)], 1.5)
        _draw_image(f"{folder}/caret-up-{key}.png", 12, t["text2"], [(3, 7.5), (6, 4.5), (9, 7.5)], 1.5)
        _draw_image(f"{folder}/check-{key}.png", 12, t["on_primary"], [(2.5, 6.2), (5, 8.6), (9.5, 3.6)], 1.8)
    QDir.setSearchPaths("of", [folder])


def build_qss(t: dict, key: str) -> str:
    """O stylesheet do app a partir dos tokens `t` do tema `key` (DARK ou LIGHT)."""
    return f"""
QWidget {{
    font-family: {_FONT_STACK};
    font-size: {FONT_PIXEL_SIZE}px;
    color: {t["text"]};
}}

QMainWindow, #homePage, #homeContent, #toolsCenter, #toolsCenterContent, #documentTab, #CenterColumn {{
    background-color: {t["bg"]};
}}

QDialog, QMessageBox {{
    background-color: {t["panel"]};
}}

QMessageBox QLabel {{
    color: {t["text"]};
}}

/* -- lateral (miniaturas, marcadores, anexos) ------------------------------------ */

#SidePanel {{
    background-color: {t["panel"]};
}}

#SideHeader {{
    border-bottom: 1px solid {t["border"]};
}}

QLabel#SideTitle {{
    font-size: 12px;
    font-weight: 600;
    color: {t["text2"]};
}}

QLabel#SideCount {{
    font-size: 12px;
    color: {t["text3"]};
}}

/* -- aviso de atualização (ui/update_dialog.py) ---------------------------------- */

QLabel#DialogTitle {{
    font-size: 17px;
    font-weight: 600;
}}

QFrame#UpdateNews {{
    background-color: {t["raised"]};
    border-radius: 8px;
}}

QTextBrowser#UpdateNotes {{
    background: transparent;
    border: none;
}}

QPushButton#BorderedGhost {{
    border: 1px solid {t["border_strong"]};
}}

/* -- tarefas (ui/widgets/task_popover.py) ----------------------------------------- */

QToolButton#TasksButton {{
    background-color: {t["raised"]};
    color: {t["text2"]};
    border-radius: 6px;
    padding: 0 8px;
    min-height: 20px;
    max-height: 20px;
    font-size: 12px;
}}

QToolButton#TasksButton:checked {{
    background-color: {t["accent_fill"]};
    color: {t["accent_strong"]};
}}

QFrame#TaskPopover {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}

QLabel#TaskPopoverTitle, QLabel#TaskName {{
    font-size: 13px;
    font-weight: 600;
}}

QFrame#TaskRow {{
    border-radius: 8px;
}}

QFrame#TaskRow[running="true"] {{
    background-color: {t["raised"]};
}}

QProgressBar#TaskProgress {{
    min-height: 4px;
    max-height: 4px;
    border-radius: 2px;
}}

QLabel {{
    background: transparent;
}}

/* -- superfícies ------------------------------------------------------------ */

#TopBar, #ViewerBar, #LeftRail, #RightRail {{
    background-color: {t["bg"]};
}}

#TopBar, #ViewerBar {{
    border-bottom: 1px solid {t["border"]};
}}

#LeftRail {{
    border-right: 1px solid {t["border"]};
}}

#RightRail {{
    border-left: 1px solid {t["border"]};
}}

QStatusBar, #StatusBar {{
    background-color: {t["bg"]};
    border-top: 1px solid {t["border"]};
    color: {t["text2"]};
    font-size: 12px;
}}

QStatusBar QLabel {{
    color: {t["text3"]};
    font-size: 12px;
}}

QStatusBar QLabel[ofRole="docState"] {{
    color: {t["text2"]};
}}

#ViewerCanvas, #ViewerCanvas > QWidget, #ViewerCanvas > QWidget > QWidget {{
    background-color: {t["canvas"]};
    border: none;
}}

#SidePanel, #ToolPanel, #viewerSidePanel {{
    background-color: {t["panel"]};
}}

/* -- painel de ferramenta (ui/tool_panel.py) ----------------------------------- */

#ToolStack {{
    background-color: {t["panel"]};
    border-left: 1px solid {t["border"]};
}}

#ToolStack[drawer="true"] {{
    border: 1px solid {t["border"]};
}}

#ToolHeader {{
    border-bottom: 1px solid {t["border"]};
}}

QLabel#IconTile {{
    background-color: {t["accent_fill"]};
    border-radius: 8px;
}}

QLabel#ToolTitle {{
    font-size: 16px;
    font-weight: 600;
}}

QLabel#ResultTitle {{
    font-weight: 600;
}}

#ToolScroll, #ToolScroll > QWidget, #ToolBody {{
    background-color: {t["panel"]};
    border: none;
}}

#ToolFooter {{
    background-color: {t["panel"]};
    border-top: 1px solid {t["border"]};
}}

QFrame#InputChip {{
    background-color: {t["raised"]};
    border-radius: 8px;
}}

QFrame#InputChip[empty="true"] {{
    background: transparent;
    border: 1px dashed {t["border_strong"]};
}}

/* Aviso do documento: formulário (acento), assinado (sucesso), protegido (aviso) e
   camadas (neutro). */
#documentNotice {{
    background-color: {t["raised"]};
}}

#documentNotice[kind="form"] {{
    background-color: {t["accent_fill"]};
}}

#documentNotice[kind="signed"] {{
    background-color: {t["success_fill"]};
}}

#documentNotice[kind="protected"] {{
    background-color: {t["warning_fill"]};
}}

#documentNotice QLabel {{
    font-size: 12px;
}}

/* -- botões de ícone (barras e trilhos) --------------------------------------- */

QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 2px;
}}

QToolButton:hover {{
    background-color: {t["hover"]};
}}

QToolButton:pressed {{
    background-color: {t["pressed"]};
}}

QToolButton:checked {{
    background-color: {t["accent_fill"]};
    border-color: {t["accent_line"]};
}}

QToolButton:focus {{
    border: 2px solid {t["focus"]};
}}

QToolButton[ofRole="icon"], QToolButton[ofRole="rail"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    min-width: 32px;
    min-height: 32px;
    padding: 0;
    color: {t["text2"]};
}}

QToolButton[ofRole="rail"] {{
    min-width: 36px;
    min-height: 36px;
}}

QToolButton[ofRole="icon"]:hover, QToolButton[ofRole="rail"]:hover {{
    background-color: {t["hover"]};
}}

QToolButton[ofRole="icon"]:pressed, QToolButton[ofRole="rail"]:pressed {{
    background-color: {t["pressed"]};
}}

QToolButton[ofRole="icon"]:checked, QToolButton[ofRole="rail"]:checked {{
    background-color: {t["accent_fill"]};
    border-color: {t["accent_line"]};
}}

QToolButton[ofRole="icon"]:disabled, QToolButton[ofRole="rail"]:disabled {{
    background: transparent;
    border-color: transparent;
}}

QToolButton[ofRole="icon"]:focus, QToolButton[ofRole="rail"]:focus {{
    border: 2px solid {t["focus"]};
}}

QToolButton#ZoomButton {{
    min-height: 32px;
    padding: 0 20px 0 8px;
    border-radius: 8px;
    color: {t["text"]};
}}

/* Ajuste e modo de exibição: ícone + seta, com menu. */
QToolButton#MenuButton {{
    padding: 0 14px 0 4px;
}}

QToolButton#NewTabButton, QToolButton#NoticeClose {{
    min-width: 28px;
    min-height: 28px;
}}

QToolButton#ZoomButton::menu-indicator, QToolButton#MenuButton::menu-indicator {{
    image: url(of:caret-down-{key}.png);
    subcontrol-origin: padding;
    subcontrol-position: right center;
    right: 6px;
    width: 10px;
    height: 10px;
}}

/* -- barra de marcação (ui/viewer/markup_bar.py) ---------------------------------- */

QFrame#MarkupBar {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}

QFrame#MarkupPopover {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}

QToolButton#MarkupTool {{
    border-radius: 8px;
    padding: 0 7px;
    color: {t["text"]};
    font-size: 12px;
    font-weight: 600;
}}

QToolButton#MarkupTool:checked {{
    color: {t["accent_strong"]};
}}

QLabel#Kbd[ofVariant="accent"] {{
    color: {t["accent_strong"]};
    border-color: {t["accent_line"]};
    padding: 1px 4px;
}}

QFrame#PendingBadge {{
    background-color: {t["accent_fill"]};
    border-radius: 12px;
}}

QLabel#PendingCount {{
    background-color: {t["primary"]};
    color: {t["on_primary"]};
    border-radius: 8px;
    font-size: 10px;
    font-weight: 700;
}}

QLabel#PendingText {{
    color: {t["accent_strong"]};
    font-size: 12px;
    font-weight: 600;
}}

QToolButton#MoreButton::menu-indicator {{
    image: none;
    width: 0;
}}

QLineEdit#PageField {{
    min-height: 28px;
    padding: 0 4px;
}}

QLineEdit#PageField:focus {{
    padding: 0 3px;
}}

QSplitter::handle {{
    background-color: {t["border"]};
}}

QPushButton#StatusCancel {{
    min-height: 22px;
    max-height: 22px;
    padding: 0 8px;
}}

/* -- botões de texto ---------------------------------------------------------- */

/* Secundário (o padrão). A borda transparente de 1 px reserva o lugar da de foco (2 px):
   no :focus o padding perde 1 px e o layout não pula. */
QPushButton {{
    min-height: 32px;
    padding: 0 14px;
    border-radius: 8px;
    border: 1px solid transparent;
    background-color: {t["raised"]};
    color: {t["text"]};
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {t["hover"]};
}}

QPushButton:pressed {{
    background-color: {t["pressed"]};
}}

/* A ferramenta escolhida (Anotações): sem isto, o botão marcado era igual aos outros. */
QPushButton:checked {{
    background-color: {t["accent_fill"]};
    border-color: {t["accent_line"]};
    color: {t["accent_strong"]};
}}

QPushButton:disabled {{
    color: {t["text3"]};
    background-color: {t["raised"]};
    border-color: transparent;
}}

QPushButton:focus {{
    border: 2px solid {t["focus"]};
    padding: 0 13px;
}}

/* Principal: só um por painel, no rodapé. */
QPushButton[ofVariant="primary"], QPushButton#primaryButton {{
    min-height: 36px;
    font-weight: 600;
    background-color: {t["primary"]};
    color: {t["on_primary"]};
}}

QPushButton[ofVariant="primary"]:hover, QPushButton#primaryButton:hover,
QPushButton[ofVariant="primary"]:pressed, QPushButton#primaryButton:pressed {{
    background-color: {t["primary_hover"]};
}}

QPushButton[ofVariant="primary"]:disabled, QPushButton#primaryButton:disabled {{
    background-color: {t["raised"]};
    color: {t["text3"]};
}}

QPushButton[ofVariant="ghost"] {{
    background: transparent;
    color: {t["text2"]};
}}

QPushButton[ofVariant="ghost"]:hover {{
    background-color: {t["hover"]};
    color: {t["text"]};
}}

QPushButton[ofVariant="ghost"]:pressed {{
    background-color: {t["pressed"]};
}}

QPushButton[ofVariant="ghost"]:disabled {{
    background: transparent;
}}

QPushButton[ofVariant="danger"] {{
    background-color: {t["danger_fill"]};
    color: {t["danger"]};
    font-weight: 600;
}}

QPushButton[ofVariant="ghost"][ofTone="danger"] {{
    color: {t["danger"]};
}}

QPushButton[ofSize="compact"] {{
    min-height: 28px;
    max-height: 28px;
    padding: 0 10px;
    border-radius: 6px;
}}

QPushButton[ofSize="compact"]:focus {{
    padding: 0 9px;
}}

QPushButton[ofSize="mini"] {{
    min-height: 24px;
    max-height: 24px;
    padding: 0 10px;
    border-radius: 6px;
    font-size: 12px;
}}

QPushButton[ofSize="mini"]:focus {{
    padding: 0 9px;
}}

/* -- selos de estado (pendente, não salvo, salvo) ------------------------------- */

QLabel[ofRole="badge"] {{
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel[ofRole="badge"][state="pending"] {{
    border: 1px dashed {t["warning"]};
    color: {t["warning"]};
}}

QLabel[ofRole="badge"][state="unsaved"] {{
    background-color: {t["accent_fill"]};
    color: {t["accent_strong"]};
}}

QLabel[ofRole="badge"][state="saved"] {{
    background-color: {t["success_fill"]};
    color: {t["success"]};
}}

/* -- campos ------------------------------------------------------------------- */

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    min-height: 32px;
    padding: 0 10px;
    border-radius: 6px;
    border: 1px solid {t["border_strong"]};
    background-color: {t["field"]};
    color: {t["text"]};
    selection-background-color: {t["accent_fill"]};
    selection-color: {t["text"]};
}}

QPlainTextEdit, QTextEdit {{
    padding: 6px 10px;
}}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover,
QPlainTextEdit:hover, QTextEdit:hover {{
    border-color: {t["text3"]};
}}

/* Campo com erro: a mensagem embaixo diz como corrigir. */
QLineEdit[state="error"], QPlainTextEdit[state="error"] {{
    border: 2px solid {t["danger"]};
    padding: 0 9px;
}}

QLabel[ofRole="error"] {{
    font-size: 12px;
    color: {t["danger"]};
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 2px solid {t["focus"]};
    padding: 0 9px;
}}

QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {t["focus"]};
    padding: 5px 9px;
}}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled {{
    color: {t["text3"]};
    background-color: {t["bg"]};
}}

QLineEdit:read-only {{
    color: {t["text2"]};
}}

QComboBox::drop-down {{
    width: 24px;
    border: 0;
}}

QComboBox::down-arrow {{
    image: url(of:caret-down-{key}.png);
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {t["accent_fill"]};
    selection-color: {t["accent_strong"]};
    outline: 0;
}}

QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QDateEdit::up-button, QDateEdit::down-button {{
    width: 20px;
    border: 0;
    background: transparent;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateEdit::up-arrow {{
    image: url(of:caret-up-{key}.png);
    width: 10px;
    height: 10px;
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateEdit::down-arrow {{
    image: url(of:caret-down-{key}.png);
    width: 10px;
    height: 10px;
}}

QDateEdit::drop-down {{
    width: 24px;
    border: 0;
}}

QCalendarWidget QAbstractItemView {{
    background-color: {t["panel"]};
    selection-background-color: {t["accent_fill"]};
    selection-color: {t["accent_strong"]};
}}

QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {t["raised"]};
}}

/* -- checkbox e radio ----------------------------------------------------------- */

QCheckBox, QRadioButton {{
    spacing: 10px;
    min-height: 28px;
    background: transparent;
}}

/* No QSS a borda soma por fora: 13 + 2 x 1,5 = 16 px no total. */
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border-radius: 4px;
    border: 1.5px solid {t["border_strong"]};
    background-color: {t["field"]};
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {t["accent"]};
}}

QCheckBox::indicator:checked {{
    background-color: {t["primary"]};
    border-color: {t["primary"]};
    image: url(of:check-{key}.png);
}}

QCheckBox::indicator:focus, QRadioButton::indicator:focus {{
    width: 12px;
    height: 12px;
    border: 2px solid {t["focus"]};
}}

QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {t["border"]};
    background-color: {t["bg"]};
}}

QCheckBox:disabled, QRadioButton:disabled {{
    color: {t["text3"]};
}}

QRadioButton::indicator {{
    width: 13px;
    height: 13px;
    border-radius: 8px;
    border: 1.5px solid {t["border_strong"]};
    background-color: {t["field"]};
}}

QRadioButton::indicator:checked {{
    width: 6px;
    height: 6px;
    border: 5px solid {t["accent"]};
    background-color: {t["field"]};
}}

QRadioButton::indicator:checked:focus {{
    border-color: {t["focus"]};
}}

/* -- segmentado e chips --------------------------------------------------------- */

#Segmented {{
    background-color: {t["field"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 2px;
}}

#Segmented QToolButton {{
    min-height: 28px;
    border-radius: 6px;
    border: 1px solid transparent;
    background: transparent;
    color: {t["text2"]};
    padding: 0 10px;
}}

#Segmented QToolButton:hover {{
    color: {t["text"]};
    background-color: {t["hover"]};
}}

#Segmented QToolButton:checked {{
    background-color: {t["raised"]};
    color: {t["text"]};
    font-weight: 500;
}}

#Segmented QToolButton:focus {{
    border: 2px solid {t["focus"]};
    padding: 0 9px;
}}

/* Pílula de filtro (24 px na lista de comentários: ofSize="small"). */
QToolButton[ofRole="chip"] {{
    min-height: 28px;
    max-height: 28px;
    border-radius: 14px;
    padding: 0 12px;
    border: 1px solid {t["border"]};
    background: transparent;
    color: {t["text2"]};
}}

QToolButton[ofRole="chip"][ofSize="small"] {{
    min-height: 24px;
    max-height: 24px;
    border-radius: 12px;
    padding: 0 10px;
}}

QToolButton[ofRole="chip"]:hover {{
    background-color: {t["hover"]};
    color: {t["text"]};
}}

QToolButton[ofRole="chip"]:checked {{
    background-color: {t["accent_fill"]};
    border-color: {t["accent_line"]};
    color: {t["accent_strong"]};
}}

QToolButton[ofRole="chip"]:focus {{
    border: 2px solid {t["focus"]};
}}

/* -- listas, árvores e tabelas -------------------------------------------------- */

QListWidget, QListView, QTreeWidget, QTreeView, QTableWidget, QTableView {{
    background-color: {t["field"]};
    alternate-background-color: {t["raised"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    outline: 0;
}}

QListWidget::item, QListView::item, QTreeWidget::item, QTreeView::item {{
    padding: 4px 6px;
    border-radius: 6px;
}}

QListWidget::item:hover:!selected, QListView::item:hover:!selected, QTreeWidget::item:hover:!selected,
QTreeView::item:hover:!selected {{
    background-color: {t["hover"]};
}}

QListWidget::item:selected, QListView::item:selected, QTreeWidget::item:selected, QTreeView::item:selected,
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {t["accent_fill"]};
    color: {t["accent_strong"]};
}}

QHeaderView::section {{
    background-color: {t["raised"]};
    color: {t["text2"]};
    border: 0;
    border-bottom: 1px solid {t["border"]};
    padding: 4px 8px;
    font-weight: 600;
}}

QTableCornerButton::section {{
    background-color: {t["raised"]};
    border: 0;
}}

QListWidget#thumbnailList {{
    background-color: {t["panel"]};
    border: none;
    border-radius: 0;
}}

/* -- Início e Ferramentas (ui/home_page.py, ui/tools_center.py) ------------------- */

QLabel#HomeTitle {{
    font-size: 24px;
    font-weight: 600;
}}

QFrame#RecentBox {{
    background-color: {t["panel"]};
    border-radius: 12px;
}}

QListWidget#RecentList, QListWidget#PaletteList {{
    background: transparent;
    border: none;
    outline: none;
}}

QToolButton#ShortcutCard {{
    border-radius: 12px;
}}

QLabel#ShortcutIconTile {{
    background-color: {t["accent_fill"]};
    border-radius: 8px;
}}

QLabel#ToolIconTile {{
    background-color: {t["raised"]};
    border-radius: 8px;
}}

QLabel#ToolCardName {{
    font-size: 13px;
    font-weight: 600;
}}

QLabel#ToolGroupTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {t["text2"]};
}}

QLineEdit#ToolSearch {{
    min-height: 44px;
    max-height: 44px;
    border-radius: 10px;
    font-size: 14px;
}}

/* -- Organizar páginas (ui/pages/organize_page.py) ------------------------------- */

#OrganizerToolbar {{
    background-color: {t["bg"]};
    border-bottom: 1px solid {t["border"]};
}}

QListWidget#OrganizerView {{
    background-color: {t["canvas"]};
    border: none;
    outline: none;
}}

QLabel#SelectionBadge {{
    background-color: {t["accent_fill"]};
    color: {t["accent_strong"]};
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 600;
}}

QToolButton[ofRole="toolbar"] {{
    min-height: 30px;
    padding: 0 8px;
    border-radius: 8px;
    color: {t["text"]};
}}

QToolButton[ofRole="toolbar"]:disabled {{
    color: {t["text3"]};
}}

QListWidget#ChangesList {{
    background: transparent;
    border: none;
}}

#ChangeRow {{
    background-color: {t["raised"]};
    border-radius: 8px;
}}

/* -- paleta de comandos (ui/shortcuts.py) ---------------------------------------- */

QFrame#CommandPalette {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}

#PaletteField {{
    border-bottom: 1px solid {t["border"]};
}}

QLineEdit#PaletteSearch {{
    font-size: 15px;
    border: none;
    background: transparent;
}}

QLineEdit#PaletteSearch:focus {{
    border: none;
}}

QLabel#PaletteCategory {{
    background-color: {t["accent_fill"]};
    border: 1px solid {t["accent_line"]};
    border-radius: 10px;
    color: {t["accent_strong"]};
    font-size: 11px;
    font-weight: 600;
    padding: 1px 8px;
}}

#PaletteFooter {{
    border-top: 1px solid {t["border"]};
}}

QListWidget#sidebar {{
    background-color: {t["panel"]};
    border: none;
    border-right: 1px solid {t["border"]};
    border-radius: 0;
    padding: 8px 0;
}}

QListWidget#sidebar::item {{
    padding: 10px 18px;
    border-radius: 0;
}}

QListWidget#sidebar::item:selected {{
    background-color: {t["accent_fill"]};
    color: {t["accent_strong"]};
}}

/* -- abas ------------------------------------------------------------------------ */

QTabWidget::pane {{
    border: 1px solid {t["border"]};
    border-radius: 8px;
    top: -1px;
    background-color: {t["panel"]};
}}

QTabBar::tab {{
    background: transparent;
    color: {t["text2"]};
    padding: 6px 14px;
    margin-right: 2px;
    border-radius: 6px;
}}

QTabBar::tab:hover:!selected {{
    background-color: {t["hover"]};
    color: {t["text"]};
}}

QTabBar::tab:selected {{
    background-color: {t["raised"]};
    color: {t["text"]};
}}

/* Abas da janela (na barra superior): Início, Ferramentas e uma por documento. */
QTabBar#DocTabs {{
    background: transparent;
}}

QTabBar#DocTabs::tab {{
    height: 32px;
    min-width: 64px;
    max-width: 200px;
    padding: 0 6px 0 10px;
    margin: 0 1px;
    border-radius: 8px;
    background: transparent;
    color: {t["text2"]};
    font-weight: 500;
}}

QTabBar#DocTabs::tab:hover:!selected {{
    background-color: {t["hover"]};
}}

QTabBar#DocTabs::tab:selected {{
    background-color: {t["raised"]};
    color: {t["text"]};
}}

QTabBar#DocTabs::tab:focus {{
    border: 2px solid {t["focus"]};
}}

QTabBar#DocTabs[compact="true"]::tab {{
    max-width: 150px;
}}

QTabBar#DocTabs QToolButton {{
    background-color: {t["bg"]};
    border: none;
    border-radius: 6px;
}}

/* -- barra superior -------------------------------------------------------------- */

QFrame#BarSeparator {{
    background-color: {t["border"]};
    border: none;
}}

QToolButton#LogoButton {{
    border-radius: 8px;
}}

QPushButton#CommandLauncher {{
    min-height: 0;
    padding: 0 10px;
    text-align: left;
    background-color: {t["field"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    color: {t["text3"]};
}}

QPushButton#CommandLauncher:hover {{
    background-color: {t["field"]};
    border-color: {t["border_strong"]};
}}

QPushButton#CommandLauncher:focus {{
    border: 2px solid {t["focus"]};
    padding: 0 9px;
}}

#Segmented QToolButton[text="PT"], #Segmented QToolButton[text="EN"] {{
    font-size: 11px;
    font-weight: 600;
    min-height: 28px;
    padding: 0 8px;
}}

/* -- menus ------------------------------------------------------------------------ */

QMenuBar {{
    background-color: {t["bg"]};
    border-bottom: 1px solid {t["border"]};
    padding: 2px 4px;
}}

QMenuBar#MainMenu {{
    background: transparent;
    border: none;
}}

QMenuBar::item {{
    min-height: 28px;
    padding: 0 8px;
    border-radius: 6px;
    background: transparent;
    color: {t["text2"]};
}}

QMenuBar::item:selected {{
    background-color: {t["hover"]};
    color: {t["text"]};
}}

QMenu {{
    background-color: {t["panel"]};
    border: 1px solid {t["border_strong"]};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px 6px 28px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background-color: {t["accent_fill"]};
    color: {t["accent_strong"]};
}}

QMenu::item:disabled {{
    color: {t["text3"]};
}}

QMenu::separator {{
    height: 1px;
    background: {t["border"]};
    margin: 4px 8px;
}}

/* -- rolagem, dicas, progresso ------------------------------------------------- */

QScrollBar:vertical {{
    width: 10px;
    background: transparent;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    min-height: 32px;
    border-radius: 3px;
    background: {t["border_strong"]};
    margin: 0 2px;
}}

QScrollBar:horizontal {{
    height: 10px;
    background: transparent;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    min-width: 32px;
    border-radius: 3px;
    background: {t["border_strong"]};
    margin: 2px 0;
}}

QScrollBar::handle:hover {{
    background: {t["text3"]};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QAbstractScrollArea::corner {{
    background: transparent;
}}

QToolTip {{
    background-color: {t["raised"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 6px 10px;
}}

QProgressBar {{
    min-height: 6px;
    max-height: 6px;
    border-radius: 3px;
    background-color: {t["raised"]};
    border: 0;
    text-align: right;
}}

QProgressBar::chunk {{
    border-radius: 3px;
    background-color: {t["accent"]};
}}

#StatusBar QProgressBar, QStatusBar QProgressBar {{
    min-height: 4px;
    max-height: 4px;
    border-radius: 2px;
}}

QSlider::groove:horizontal {{
    height: 4px;
    border-radius: 2px;
    background: {t["border_strong"]};
}}

QSlider::sub-page:horizontal {{
    border-radius: 2px;
    background: {t["accent"]};
}}

QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -6px 0;
    border-radius: 8px;
    background: {t["text"]};
    border: 2px solid {t["bg"]};
}}

/* -- textos, cartões e estados -------------------------------------------------- */

QLabel#pageTitle {{
    font-size: 24px;
    font-weight: 600;
}}

QLabel#pageSubtitle, QLabel[ofRole="secondary"] {{
    font-size: 12px;
    color: {t["text2"]};
}}

QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 600;
}}

/* Rótulo de seção em frase normal ("Arquivo", "Onde fica o resultado"), sem caixa alta. */
QLabel[ofRole="section"] {{
    font-size: 12px;
    font-weight: 600;
    color: {t["text2"]};
}}

QLabel[ofRole="help"] {{
    font-size: 12px;
    color: {t["text3"]};
}}

QLabel#documentSourceLabel {{
    color: {t["text2"]};
}}

QLabel#Kbd {{
    font-size: 11px;
    color: {t["text2"]};
    border: 1px solid {t["border_strong"]};
    border-radius: 4px;
    padding: 1px 6px;
}}

QFrame[ofRole="card"] {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QToolButton[ofRole="card"], QToolButton#toolCard {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 10px 12px;
}}

QToolButton[ofRole="card"]:hover, QToolButton#toolCard:hover {{
    background-color: {t["raised"]};
    border-color: {t["border_strong"]};
}}

QToolButton[ofRole="card"]:focus, QToolButton#toolCard:focus {{
    border: 2px solid {t["focus"]};
}}

QFrame[ofRole="result"][state="success"] {{
    background-color: {t["success_fill"]};
    border-radius: 8px;
}}

QFrame[ofRole="result"][state="error"] {{
    background-color: {t["danger_fill"]};
    border-radius: 8px;
}}

QFrame[ofRole="result"][state="warning"] {{
    background-color: {t["warning_fill"]};
    border-radius: 8px;
}}

QFrame[ofRole="result"][state="info"] {{
    background-color: {t["raised"]};
    border-radius: 8px;
}}

#ViewerEmpty {{
    background-color: {t["canvas"]};
}}

QLabel#EmptyTitle {{
    font-size: 17px;
    font-weight: 600;
}}

QFrame#DropZone {{
    border: 1.5px dashed {t["border_strong"]};
    border-radius: 12px;
    background-color: {t["panel"]};
}}

QFrame#DropZone[dragOver="true"] {{
    border-color: {t["accent"]};
    background-color: {t["accent_fill"]};
}}
"""


def _palette(t: dict) -> QPalette:
    palette = QPalette()
    roles = QPalette.ColorRole
    for role, key in (
        (roles.Window, "bg"),
        (roles.WindowText, "text"),
        (roles.Base, "field"),
        (roles.AlternateBase, "raised"),
        (roles.ToolTipBase, "panel"),
        (roles.ToolTipText, "text"),
        (roles.Text, "text"),
        (roles.Button, "raised"),
        (roles.ButtonText, "text"),
        (roles.Light, "raised"),
        (roles.Midlight, "hover"),
        (roles.Mid, "border"),
        (roles.Dark, "border_strong"),
        (roles.Link, "accent_strong"),
        (roles.LinkVisited, "accent_strong"),
        (roles.Highlight, "primary"),
        (roles.HighlightedText, "on_primary"),
        (roles.PlaceholderText, "text3"),
    ):
        palette.setColor(role, QColor(t[key]))
    for role in (roles.Text, roles.ButtonText, roles.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["text3"]))
    return palette


def resolved_theme(theme: str) -> str:
    """DARK ou LIGHT: SYSTEM vira o esquema de cores do sistema (escuro se ele não disser)."""
    if theme == SYSTEM:
        scheme = QGuiApplication.styleHints().colorScheme()
        return LIGHT if scheme == Qt.ColorScheme.Light else DARK
    return theme if theme in TOKENS else DARK


def current_theme() -> str:
    """O tema aplicado agora (DARK ou LIGHT)."""
    return _current


def apply_theme(app: QApplication, theme: str = DARK) -> None:
    """Aplica o tema a toda a aplicação, inclusive às janelas já abertas. Os ícones
    desenhados pelo app (`ui/icon_utils.py`) leem `icon_color` ao pintar e seguem sozinhos."""
    global _current
    _current = resolved_theme(theme)
    t = TOKENS[_current]
    load_fonts()
    _ensure_images()
    font = QFont()
    font.setFamilies([FONT_FAMILY, "Segoe UI", "Cantarell", "SF Pro Text"])
    font.setPixelSize(FONT_PIXEL_SIZE)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setPalette(_palette(t))
    app.setStyleSheet(build_qss(t, _current))
    for window in app.topLevelWidgets():
        if window.isWindow() and window.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            apply_titlebar(window)


def apply_titlebar(window: QWidget) -> None:
    """No Windows, a barra de título nativa acompanha o tema (o DWM não segue a paleta do Qt)."""
    if sys.platform != "win32":
        return

    if QApplication.platformName() == "offscreen":
        return

    import ctypes

    hwnd = int(window.winId())
    value = ctypes.c_int(1 if _current == DARK else 0)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE varia por build do Windows
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
        )
        if result == 0:
            break
