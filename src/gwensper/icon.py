"""Icono de Gwensper dibujado con QPainter (sin archivos binarios obligatorios)."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap

# Paleta inspirada en Gwen: tinta, porcelana, azul de su cabello y niebla consagrada.
INK_TOP = QColor("#232A52")
INK_BOTTOM = QColor("#1A1F3D")
PORCELAIN = QColor("#F2F4FA")
GWEN_BLUE = QColor("#7FB3F5")
MIST = QColor("#9FF3F0")


def draw_mic(p: QPainter, rect: QRectF, color: QColor) -> None:
    """Dibuja un micrófono centrado en `rect`."""
    w, h = rect.width(), rect.height()
    cx = rect.center().x()
    pen = QPen(color, max(1.2, w * 0.085), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    body = QRectF(cx - w * 0.17, rect.top() + h * 0.08, w * 0.34, h * 0.52)
    p.drawRoundedRect(body, w * 0.17, w * 0.17)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    arc = QRectF(cx - w * 0.30, rect.top() + h * 0.22, w * 0.60, h * 0.52)
    p.drawArc(arc, 200 * 16, 140 * 16)
    p.drawLine(QPointF(cx, rect.top() + h * 0.74), QPointF(cx, rect.top() + h * 0.88))
    p.drawLine(QPointF(cx - w * 0.16, rect.top() + h * 0.90), QPointF(cx + w * 0.16, rect.top() + h * 0.90))


def render(size: int = 256) -> QPixmap:
    """Botón de costura azul tinta con puntadas alrededor y un micrófono de porcelana."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    m = size * 0.03
    outer = QRectF(m, m, size - 2 * m, size - 2 * m)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, INK_TOP)
    grad.setColorAt(1, INK_BOTTOM)
    p.setPen(QPen(GWEN_BLUE, max(1.0, size * 0.02)))
    p.setBrush(grad)
    p.drawEllipse(outer)
    if size >= 32:
        # Costura: se omite en tamaños diminutos donde solo sería ruido.
        stitch = QPen(MIST, size * 0.028, Qt.CustomDashLine, Qt.RoundCap)
        stitch.setDashPattern([2.2, 2.0])
        p.setPen(stitch)
        p.setBrush(Qt.NoBrush)
        inset = size * 0.11
        p.drawEllipse(outer.adjusted(inset, inset, -inset, -inset))
    draw_mic(p, QRectF(size * 0.30, size * 0.21, size * 0.40, size * 0.58), PORCELAIN)
    p.end()
    return pm


def asset_path(name: str) -> Path | None:
    try:
        path = Path(str(resources.files("gwensper") / "assets" / name))
    except (ModuleNotFoundError, TypeError):
        return None
    return path if path.exists() else None


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render(s))
    return icon


def save_ico(path: Path) -> Path:
    """Guarda un .ico multi-resolución (usado por el acceso directo de Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    render(256).save(str(path), "ICO")
    return path
