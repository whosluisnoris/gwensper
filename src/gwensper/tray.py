"""Icono y menú en la bandeja del sistema."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icon import app_icon


class Tray(QSystemTrayIcon):
    toggle_requested = Signal()
    open_requested = Signal()
    settings_requested = Signal()
    overlay_toggled = Signal(bool)
    autostart_toggled = Signal(bool)
    open_folder_requested = Signal()
    quit_requested = Signal()

    def __init__(self, hotkey_label: str, overlay_always: bool, autostart: bool):
        super().__init__(app_icon())
        self.menu = QMenu()
        self.menu.addAction("Abrir Gwensper", self.open_requested)
        self.act_toggle = QAction(self.menu)
        self.act_toggle.triggered.connect(self.toggle_requested)
        self.menu.addAction(self.act_toggle)
        self.menu.addSeparator()

        self.act_overlay = QAction("Mostrar siempre el indicador", self.menu, checkable=True,
                                   checked=overlay_always)
        self.act_overlay.toggled.connect(self.overlay_toggled)
        self.menu.addAction(self.act_overlay)
        self.act_autostart = QAction("Iniciar con Windows", self.menu, checkable=True, checked=autostart)
        self.act_autostart.toggled.connect(self.autostart_toggled)
        self.menu.addAction(self.act_autostart)
        self.menu.addAction("Configuración…", self.settings_requested)
        self.menu.addAction("Abrir carpeta de configuración", self.open_folder_requested)
        self.menu.addSeparator()
        self.menu.addAction("Salir", self.quit_requested)
        self.setContextMenu(self.menu)

        self.activated.connect(self._on_activated)
        self.hotkey_label = hotkey_label
        self.set_listening(False)

    def set_listening(self, listening: bool) -> None:
        verb = "Detener dictado" if listening else "Iniciar dictado"
        self.act_toggle.setText(f"{verb}\t{self.hotkey_label}")

    def set_status(self, text: str) -> None:
        self.setToolTip(f"Gwensper — {text}")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.open_requested.emit()
