"""Animações da interface, que respeitam Exibir > Animações da interface."""

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation

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
