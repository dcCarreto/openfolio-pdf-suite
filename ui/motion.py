"""Animações da interface, que respeitam Exibir > Animações da interface."""

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QVariantAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from ui.preferences import preferences

FAST, MEDIUM, SLOW = 120, 160, 200  # ms


def enabled() -> bool:
    return preferences().animations()


def animate(target: QObject, prop: bytes, start, end, ms: int, curve=QEasingCurve.Type.OutCubic, on_done=None):
    """Anima `prop` de `target`. Com as animações desligadas, aplica `end` direto. A animação
    fica guardada no próprio alvo (uma por propriedade), para não ser coletada no meio."""
    running = getattr(target, "_of_animations", {})
    if (previous := running.get(prop)) is not None:
        previous.stop()
    if not enabled():
        target.setProperty(prop.decode(), end)
        if on_done is not None:
            on_done()
        return None
    animation = QPropertyAnimation(target, prop, target)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setDuration(ms)
    animation.setEasingCurve(curve)
    if on_done is not None:
        animation.finished.connect(on_done)
    running[prop] = animation
    target._of_animations = running  # type: ignore[attr-defined]
    animation.start()
    return animation


def animate_value(owner: QObject, start, end, ms: int, on_value, on_done=None, curve=QEasingCurve.Type.OutCubic):
    """Um valor de `start` a `end` (o tamanho do painel no divisor), entregue a `on_value` a
    cada passo. Com as animações desligadas, entrega `end` direto."""
    running = getattr(owner, "_of_value_animation", None)
    if running is not None:
        running.stop()
    if not enabled():
        on_value(end)
        if on_done is not None:
            on_done()
        return None
    animation = QVariantAnimation(owner)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setDuration(ms)
    animation.setEasingCurve(curve)
    animation.valueChanged.connect(on_value)
    if on_done is not None:
        animation.finished.connect(on_done)
    owner._of_value_animation = animation  # type: ignore[attr-defined]
    animation.start()
    return animation


def fade_in(widget: QWidget, ms: int, then=None):
    """Opacidade de 0 a 1; ao terminar, o efeito sai (nenhum efeito fica pendurado) e `then`
    roda (a gaveta põe a sombra de volta)."""

    def finish():
        widget.setGraphicsEffect(None)  # type: ignore[arg-type]
        if then is not None:
            then()

    if not enabled():
        finish()
        return None
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    return animate(effect, b"opacity", 0.0, 1.0, ms, on_done=finish)
