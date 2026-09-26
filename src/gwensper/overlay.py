"""Indicador flotante: un parche de tela cosido, inspirado en Gwen, la costurera consagrada.

- Listo: puntadas quietas.
- Escuchando: la puntada recorre el borde (más viva cuanto más fuerte hablas) y la
  niebla consagrada rodea el botón.
- Descargando: hilo dorado que va cosiendo el borde según el progreso.
- Transcribiendo: unas tijeras hacen "snip".

No roba el foco de la app donde escribes.
"""
from __future__ import annotations

import ctypes
import math

from PySide6.QtCore import QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import winapi
from .fonts import ui_font
from .icon import GWEN_BLUE, INK_BOTTOM, INK_TOP, MIST, PORCELAIN, draw_mic

HEIGHT = 46
BUTTON = 28
STITCH_INSET = 5.0
# El botón es concéntrico con el arco izquierdo de la costura: queda un margen parejo
# de (HEIGHT/2 - STITCH_INSET) - BUTTON/2 = 4 px entre el botón y las puntadas.
BUTTON_CENTER = QPointF(HEIGHT / 2, HEIGHT / 2)
TEXT_X = HEIGHT / 2 + BUTTON / 2 + 11
SCISSORS_W = 30

GOLD_THREAD = QColor("#E4C57A")
RIBBON_ROSE = QColor("#E8798E")

BUTTON_COLOR = {"idle": GWEN_BLUE, "loading": GOLD_THREAD, "listening": MIST, "error": RIBBON_ROSE}


def _with_alpha(c: QColor, a: int) -> QColor:
    c = QColor(c)
    c.setAlpha(max(0, min(255, a)))
    return c


def _animations_enabled() -> bool:
    """Respeta 'Efectos de animación' desactivado en Windows."""
    if not winapi.IS_WINDOWS:
        return True
    value = ctypes.c_int(1)
    SPI_GETCLIENTAREAANIMATION = 0x1042
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0):
        return bool(value.value)
    return True


def draw_scissors(p: QPainter, center: QPointF, size: float, opening_deg: float, color: QColor) -> None:
    """Tijeras vistas de lado; cada hoja es una palanca que gira sobre el pivote."""
    for sign in (1, -1):
        p.save()
        p.translate(center)
        p.rotate(sign * opening_deg)
        p.setPen(Qt.NoPen)
        p.setBrush(PORCELAIN)
        blade = QPolygonF([QPointF(0, -1.3 * sign), QPointF(size * 0.55, 0), QPointF(0, 1.0 * sign)])
        p.drawPolygon(blade)
        p.setPen(QPen(color, 1.6))
        p.setBrush(Qt.NoBrush)
        r = size * 0.15
        p.drawEllipse(QPointF(-size * 0.32, 0), r, r)
        p.restore()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(center, 1.4, 1.4)


class Overlay(QWidget):
    clicked = Signal()
    context_requested = Signal(QPoint)
    moved = Signal(int, int)

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Gwensper")
        self.setCursor(Qt.PointingHandCursor)
        self.font_ = ui_font(11.5, QFont.Medium)

        self.state = "loading"
        self.text = "Iniciando"
        self.level = 0.0
        self.busy = False
        self.progress = -1
        self.animate = _animations_enabled()
        self._phase = 0.0
        self._stitch_offset = 0.0
        self._stitch_speed = 0.0
        self._thread_cache: tuple[int, tuple[float, int]] = (-1, (0.0, 1))
        self._press: QPoint | None = None
        self._origin = QPoint()
        self._dragging = False

        self._timer = QTimer(self, interval=33, timeout=self._tick)
        self._timer.start()
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(160)
        self._fade.finished.connect(self._on_fade_done)
        self._relayout()

    # ---------- API ----------
    def set_state(self, state: str, text: str) -> None:
        self.state, self.text = state, text
        if state != "loading":
            self.progress = -1
        self._relayout()
        self.update()

    def set_level(self, level: float) -> None:
        self.level = 0.6 * self.level + 0.4 * level

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.update()

    def set_progress(self, pct: int) -> None:
        self.progress = pct
        if 0 <= pct < 100:
            self.text = f"Descargando modelo, {pct} %"
        self._relayout()
        self.update()

    def appear(self) -> None:
        """Muestra la píldora con un fundido corto (sin robar el foco)."""
        self._fade.stop()
        if not self.isVisible():
            self.setWindowOpacity(0.0 if self.animate else 1.0)
            self.show()
        if self.animate:
            self._fade.setStartValue(self.windowOpacity())
            self._fade.setEndValue(1.0)
            self._fade.start()

    def disappear(self) -> None:
        if not self.isVisible():
            return
        self._fade.stop()
        if not self.animate:
            self.hide()
            return
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_done(self) -> None:
        if self.windowOpacity() < 0.01:
            self.hide()
            self.setWindowOpacity(1.0)

    def place(self, x: int | None, y: int | None) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if x is None or y is None or not any(
            s.availableGeometry().contains(QPoint(x + 10, y + 10)) for s in QGuiApplication.screens()
        ):
            x = screen.center().x() - self.width() // 2
            y = screen.bottom() - HEIGHT - 24
        self.move(x, y)

    # ---------- animación ----------
    def _extra_width(self) -> int:
        # Espacio reservado para las tijeras mientras se dicta (evita saltos de tamaño).
        return SCISSORS_W if self.state == "listening" else 0

    def _relayout(self) -> None:
        tw = QFontMetrics(self.font_).horizontalAdvance(self.text)
        self.setFixedSize(int(TEXT_X + tw + 20 + self._extra_width()), HEIGHT)

    def _tick(self) -> None:
        if not self.animate:
            return
        self._phase = (self._phase + 0.12) % (2 * math.pi * 1000)
        if self.state == "listening":
            # La puntada avanza sin prisa y acelera cuanto más fuerte se habla;
            # la velocidad se suaviza para que no cambie de golpe.
            target = 0.12 + 1.5 * self.level
            self._stitch_speed += 0.15 * (target - self._stitch_speed)
            self._stitch_offset -= self._stitch_speed
        else:
            self.level *= 0.8
        if self.state in ("listening", "loading") or self.busy:
            self.update()

    # ---------- dibujo ----------
    def _patch_path(self, inset: float) -> QPainterPath:
        r = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        return path

    def _draw_stitches(self, p: QPainter) -> None:
        path = self._patch_path(STITCH_INSET)
        pen = QPen(Qt.SolidLine)
        pen.setWidthF(1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setDashPattern([3.0, 2.8])

        if self.state == "listening":
            pen.setColor(_with_alpha(MIST, 110 + int(140 * self.level)))
            pen.setDashOffset(self._stitch_offset)
        elif self.state == "error":
            pen.setColor(_with_alpha(RIBBON_ROSE, 170))
        else:
            pen.setColor(_with_alpha(PORCELAIN, 55))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        if self.state == "loading" and 0 <= self.progress <= 100:
            # Hilo dorado cosiendo el borde según el progreso: empieza arriba a la izquierda
            # y avanza en sentido horario, como una barra de progreso.
            if self._thread_cache[0] != self.width():
                self._thread_cache = (self.width(), self._thread_start(path))
            start, direction = self._thread_cache[1]
            frac = 0.999 * self.progress / 100
            steps = max(2, int(160 * frac))
            pts = [path.pointAtPercent((start + direction * frac * i / (steps - 1)) % 1.0)
                   for i in range(steps)]
            gold = QPen(pen)
            gold.setColor(GOLD_THREAD)
            gold.setWidthF(1.8)
            gold.setDashOffset(0)
            p.setPen(gold)
            p.drawPolyline(QPolygonF(pts))

    @staticmethod
    def _thread_start(path: QPainterPath) -> tuple[float, int]:
        """Punto del contorno donde empieza el borde superior recto, y el sentido hacia la derecha."""
        r = path.boundingRect()
        target = QPointF(r.left() + r.height() / 2, r.top())
        samples = 400
        start = min(
            (i / samples for i in range(samples)),
            key=lambda t: (path.pointAtPercent(t) - target).manhattanLength(),
        )
        ahead = path.pointAtPercent((start + 0.01) % 1.0)
        return start, 1 if ahead.x() > target.x() else -1

    def _draw_button(self, p: QPainter) -> None:
        color = BUTTON_COLOR.get(self.state, GWEN_BLUE)
        center = BUTTON_CENTER
        c = QRectF(center.x() - BUTTON / 2, center.y() - BUTTON / 2, BUTTON, BUTTON)

        if self.state == "listening":
            # Niebla consagrada: se expande con la voz.
            breathe = 0.5 + 0.5 * math.sin(self._phase) if self.animate else 0.5
            radius = BUTTON / 2 + 3 + 5 * self.level + 2 * breathe
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0.55, _with_alpha(MIST, 120))
            glow.setColorAt(1.0, _with_alpha(MIST, 0))
            p.save()
            p.setClipPath(self._patch_path(1))  # la niebla queda dentro del parche
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(center, radius, radius)
            p.restore()

        p.setPen(QPen(_with_alpha(PORCELAIN, 170), 1.2))
        p.setBrush(color)
        p.drawEllipse(c)
        draw_mic(p, c.adjusted(7.5, 6, -7.5, -6), INK_BOTTOM)

        # Girando: cargando sin porcentaje, o terminando de escribir tras detener.
        if (self.state == "loading" and self.progress < 0) or (self.state == "idle" and self.busy):
            spin = QPen(GOLD_THREAD, 2, Qt.SolidLine, Qt.RoundCap)
            p.setPen(spin)
            p.setBrush(Qt.NoBrush)
            start = int(-math.degrees(self._phase) * 16) % (360 * 16)
            p.drawArc(c.adjusted(-2.5, -2.5, 2.5, 2.5), start, 100 * 16)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        body = self._patch_path(0.5)
        grad = QLinearGradient(0, 0, 0, HEIGHT)
        grad.setColorAt(0, _with_alpha(INK_TOP, 245))
        grad.setColorAt(1, _with_alpha(INK_BOTTOM, 245))
        p.fillPath(body, grad)
        p.setPen(QPen(_with_alpha(GWEN_BLUE, 70), 1))
        p.drawPath(body)

        self._draw_stitches(p)
        self._draw_button(p)

        p.setFont(self.font_)
        p.setPen(PORCELAIN if self.state != "error" else _with_alpha(RIBBON_ROSE, 255).lighter(130))
        p.drawText(QRectF(TEXT_X, 0, self.width() - TEXT_X - self._extra_width(), HEIGHT - 1),
                   Qt.AlignVCenter, self.text)

        if self.state == "listening" and self.busy:
            snip = abs(math.sin(self._phase * 1.6)) if self.animate else 0.6
            center = QPointF(self.width() - SCISSORS_W / 2 - 10, HEIGHT / 2)
            draw_scissors(p, center, 21, 6 + 22 * snip, GOLD_THREAD)
        p.end()

    # ---------- interacción ----------
    def showEvent(self, e):
        super().showEvent(e)
        if winapi.IS_WINDOWS:
            winapi.make_no_activate(int(self.winId()))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._origin = self.pos()
            self._dragging = False
        elif e.button() == Qt.RightButton:
            self.context_requested.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        delta = e.globalPosition().toPoint() - self._press
        if self._dragging or delta.manhattanLength() > 4:
            self._dragging = True
            self.move(self._origin + delta)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._press is None:
            return
        if self._dragging:
            self.moved.emit(self.x(), self.y())
        else:
            self.clicked.emit()
        self._press = None
        self._dragging = False
