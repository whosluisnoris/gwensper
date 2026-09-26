"""Inserta el texto dictado en la ventana que tiene el foco."""
from __future__ import annotations

import logging

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtGui import QGuiApplication

from . import winapi

log = logging.getLogger(__name__)


class Typer:
    def __init__(self, mode: str = "type"):
        self.mode = mode

    def insert(self, text: str) -> None:
        """Debe llamarse desde el hilo de la interfaz (usa el portapapeles de Qt)."""
        if not text:
            return
        if self.mode == "paste":
            self._paste(text)
        else:
            winapi.type_unicode(text)

    def _paste(self, text: str) -> None:
        cb = QGuiApplication.clipboard()
        saved = QMimeData()
        old = cb.mimeData()
        if old is not None:
            for fmt in old.formats():
                saved.setData(fmt, old.data(fmt))
        cb.setText(text)
        winapi.send_ctrl_v()
        # Devuelve el portapapeles anterior cuando la app ya pegó.
        QTimer.singleShot(400, lambda: cb.setMimeData(saved))
