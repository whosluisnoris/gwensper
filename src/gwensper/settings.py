"""Ventana de configuración."""
from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QMessageBox, QSpinBox, QVBoxLayout,
)

from .audio import list_input_devices
from .config import DEFAULT_MODEL, MODELS, Config
from .icon import app_icon
from .winapi import parse_hotkey

LANGUAGES = [
    ("", "Detectar automáticamente"), ("es", "Español"), ("en", "Inglés"), ("pt", "Portugués"),
    ("fr", "Francés"), ("it", "Italiano"), ("de", "Alemán"), ("ca", "Catalán"),
    ("nl", "Neerlandés"), ("ru", "Ruso"), ("ja", "Japonés"), ("zh", "Chino"), ("ko", "Coreano"),
]
DEVICES = [("auto", "Automático (GPU si hay, si no CPU)"), ("cpu", "Solo CPU"), ("cuda", "GPU NVIDIA")]
MODEL_HINTS = {
    "tiny": "tiny — muy rápido, menos preciso",
    "base": "base — rápido, para PCs modestos",
    "small": "small — buen equilibrio en CPU",
    "medium": "medium — preciso, lento en CPU",
    "large-v3-turbo": "large-v3-turbo — muy preciso (recomendado con GPU)",
    "large-v3": "large-v3 — máxima precisión, pesado",
}


def _combo(items, current) -> QComboBox:
    box = QComboBox()
    for value, label in items:
        box.addItem(label, value)
    idx = box.findData(current)
    box.setCurrentIndex(max(0, idx))
    return box


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, status: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gwensper — Configuración")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(460)
        self.cfg = dataclasses.replace(cfg)

        self.hotkey = QLineEdit(cfg.hotkey)
        self.hotkey.setPlaceholderText("ej. ctrl+alt+d, ctrl+shift+space, f9")
        self.language = _combo(LANGUAGES, cfg.language)
        self.device = _combo(DEVICES, cfg.device)
        auto_label = f"Automático ({DEFAULT_MODEL['cpu']} en CPU, {DEFAULT_MODEL['cuda']} en GPU)"
        self.model = _combo([("", auto_label)] + [(m, MODEL_HINTS[m]) for m in MODELS], cfg.model)
        mics = list_input_devices()
        if cfg.input_device and cfg.input_device not in mics:
            mics.append(cfg.input_device)
        self.mic = _combo([("", "Predeterminado del sistema")] + [(m, m) for m in mics], cfg.input_device)
        self.silence = QSpinBox(minimum=250, maximum=3000, singleStep=50, suffix=" ms")
        self.silence.setValue(cfg.silence_ms)
        self.sensitivity = QDoubleSpinBox(minimum=1.5, maximum=10.0, singleStep=0.5, decimals=1)
        self.sensitivity.setValue(cfg.sensitivity)
        self.sensitivity.setToolTip("Más alto = ignora más ruido de fondo, pero necesitas hablar más fuerte.")
        self.insert_mode = _combo([("type", "Teclear (no usa el portapapeles)"), ("paste", "Pegar (Ctrl+V)")],
                                  cfg.insert_mode)

        form = QFormLayout()
        form.addRow("Atajo para dictar:", self.hotkey)
        form.addRow("Idioma:", self.language)
        form.addRow("Procesar con:", self.device)
        form.addRow("Modelo:", self.model)
        form.addRow("Micrófono:", self.mic)
        form.addRow("Pausa que cierra una frase:", self.silence)
        form.addRow("Umbral de voz:", self.sensitivity)
        form.addRow("Cómo escribir:", self.insert_mode)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        if status:
            info = QLabel(status)
            info.setStyleSheet("color: gray;")
            layout.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        hotkey = self.hotkey.text().strip().lower()
        try:
            parse_hotkey(hotkey)
        except ValueError as e:
            QMessageBox.warning(self, "Atajo inválido", f"No entiendo el atajo «{hotkey}»: {e}")
            return
        self.cfg.hotkey = hotkey
        self.cfg.language = self.language.currentData()
        self.cfg.device = self.device.currentData()
        self.cfg.model = self.model.currentData()
        self.cfg.input_device = self.mic.currentData()
        self.cfg.silence_ms = self.silence.value()
        self.cfg.sensitivity = self.sensitivity.value()
        self.cfg.insert_mode = self.insert_mode.currentData()
        self.accept()
