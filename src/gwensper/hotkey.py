"""Atajo global con RegisterHotKey de Windows (funciona aunque Gwensper no tenga el foco)."""
from __future__ import annotations

import logging
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

from . import winapi

log = logging.getLogger(__name__)

HOTKEY_ID = 0x6757  # "gW"


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback: Callable[[], None]):
        super().__init__()
        self.callback = callback
        self.hwnd = 0
        self.spec = ""
        QCoreApplication.instance().installNativeEventFilter(self)

    def register(self, hwnd: int, spec: str) -> bool:
        """Registra (o reemplaza) el atajo. Devuelve False si otra app ya lo usa."""
        self.unregister()
        try:
            ok = winapi.register_hotkey(hwnd, HOTKEY_ID, spec)
        except ValueError as e:
            log.warning("Atajo inválido '%s': %s", spec, e)
            return False
        if ok:
            self.hwnd, self.spec = hwnd, spec
            log.info("Atajo registrado: %s", spec)
        else:
            log.warning("No se pudo registrar el atajo %s (¿en uso?)", spec)
        return ok

    def unregister(self) -> None:
        if self.hwnd:
            winapi.unregister_hotkey(self.hwnd, HOTKEY_ID)
            self.hwnd = 0

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == winapi.WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.callback()
                return True, 0
        return False, 0
