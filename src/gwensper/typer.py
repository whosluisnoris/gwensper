"""Inserta el texto dictado en la ventana que tiene el foco, palabra por palabra."""
from __future__ import annotations

import logging
import re
from collections import deque

from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from . import winapi

log = logging.getLogger(__name__)

WORD_INTERVAL_MS = 40
_TOKEN_RE = re.compile(r"\S+\s*|\s+")


def tokenize(text: str) -> list[str]:
    """Parte el texto en palabras, cada una con el espacio que la sigue (sin perder nada)."""
    return _TOKEN_RE.findall(text)


class Typer(QObject):
    """Cola de escritura: cada tick escribe una palabra. Debe vivir en el hilo de la interfaz."""

    idle = Signal()

    def __init__(self, mode: str = "type"):
        super().__init__()
        self.mode = mode
        self._queue: deque[str] = deque()
        self._timer = QTimer(self, interval=WORD_INTERVAL_MS, timeout=self._type_next)
        self._saved_clipboard: QMimeData | None = None

    @property
    def busy(self) -> bool:
        return bool(self._queue)

    def insert(self, text: str) -> None:
        if not text:
            return
        # En modo pegar va la frase completa: pegar palabra por palabra ensuciaría el portapapeles.
        self._queue.extend([text] if self.mode == "paste" else tokenize(text))
        if not self._timer.isActive():
            self._type_next()
            if self._queue:
                self._timer.start()

    def _type_next(self) -> None:
        if self._queue:
            token = self._queue.popleft()
            try:
                if self.mode == "paste":
                    self._paste(token)
                else:
                    winapi.type_unicode(token)
            except OSError:
                log.exception("No se pudo escribir el texto")
        if not self._queue:
            self._timer.stop()
            self.idle.emit()

    def _paste(self, text: str) -> None:
        cb = QGuiApplication.clipboard()
        if self._saved_clipboard is None:
            # Guarda el portapapeles del usuario solo una vez, aunque se peguen varias frases seguidas.
            saved = QMimeData()
            old = cb.mimeData()
            if old is not None:
                for fmt in old.formats():
                    saved.setData(fmt, old.data(fmt))
            self._saved_clipboard = saved
        cb.setText(text)
        winapi.send_ctrl_v()
        QTimer.singleShot(400, self._restore_clipboard)

    def _restore_clipboard(self) -> None:
        if self._saved_clipboard is None or self._queue:
            return  # todavía quedan frases por pegar
        QGuiApplication.clipboard().setMimeData(self._saved_clipboard)
        self._saved_clipboard = None
