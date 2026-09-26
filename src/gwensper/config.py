"""Configuración persistente en %APPDATA%\\Gwensper\\config.json."""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import APP_NAME

log = logging.getLogger(__name__)

# Modelo y tipo de cómputo por defecto según el dispositivo.
DEFAULT_MODEL = {"cpu": "small", "cuda": "large-v3-turbo"}
COMPUTE_TYPE = {"cpu": "int8", "cuda": "int8_float16"}
MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


def _store_python_family() -> str | None:
    """Nombre de familia del paquete si se ejecuta con Python de la Microsoft Store.

    Ej.: sys.base_prefix = ...\\WindowsApps\\PythonSoftwareFoundation.Python.3.11_3.11.2544.0_x64__qbz5n2kfra8p0
    -> "PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0".
    """
    # base_prefix: dentro de un entorno virtual creado con Python de la Store, la
    # redirección de %APPDATA% sigue aplicando.
    name = Path(sys.base_prefix).name
    if "\\windowsapps\\" not in sys.base_prefix.lower() or "__" not in name:
        return None
    return f"{name.split('_')[0]}_{name.rsplit('__', 1)[1]}"


def data_dir() -> Path:
    # Python de la Store redirige en silencio las escrituras en %APPDATA% a su carpeta
    # privada; usamos esa ruta física directamente para poder mostrarla y abrirla.
    family = _store_python_family()
    local = os.environ.get("LOCALAPPDATA")
    if family and local:
        return Path(local) / "Packages" / family / "LocalCache" / "Roaming" / APP_NAME
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def config_path() -> Path:
    return data_dir() / "config.json"


@dataclass
class Config:
    hotkey: str = "ctrl+alt+d"
    language: str = "es"          # "" = detección automática
    device: str = "auto"          # auto | cpu | cuda
    model: str = ""               # "" = según el dispositivo (DEFAULT_MODEL)
    input_device: str = ""        # "" = micrófono predeterminado
    silence_ms: int = 600         # silencio que cierra una frase
    max_phrase_s: float = 20.0    # corta frases muy largas
    sensitivity: float = 3.0      # umbral de voz = ruido de fondo x sensibilidad
    insert_mode: str = "type"     # type | paste
    live_mode: str = "auto"       # auto (en vivo solo con GPU) | on | off
    overlay_always: bool = False  # False = la píldora solo aparece mientras dictas
    overlay_x: int | None = None
    overlay_y: int | None = None
    first_run_done: bool = False
    window_hint_shown: bool = False

    def model_for(self, device: str) -> str:
        return self.model or DEFAULT_MODEL[device]

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as e:
            log.warning("Config inválida (%s); usando valores por defecto", e)
            return cls()
        cfg = cls()
        for f in fields(cls):
            if f.name not in raw:
                continue
            value, default = raw[f.name], getattr(cfg, f.name)
            # Acepta el valor solo si coincide con el tipo esperado (None permitido en posiciones).
            if default is None or value is None or isinstance(value, type(default)) or (
                isinstance(default, float) and isinstance(value, int)
            ):
                setattr(cfg, f.name, value)
        if cfg.device not in ("auto", "cpu", "cuda"):
            cfg.device = "auto"
        if cfg.insert_mode not in ("type", "paste"):
            cfg.insert_mode = "type"
        if cfg.live_mode not in ("auto", "on", "off"):
            cfg.live_mode = "auto"
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
