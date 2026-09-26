"""Fuente de la interfaz: Bricolage Grotesque (Google Fonts, SIL OFL 1.1), incluida en assets/fonts."""
from __future__ import annotations

import logging

from PySide6.QtGui import QFont, QFontDatabase

from .icon import asset_path

log = logging.getLogger(__name__)

FAMILY = "Bricolage Grotesque"
FALLBACK = "Segoe UI"
_family: str | None = None


def load() -> str:
    """Registra la fuente incluida (una sola vez). Requiere una QGuiApplication creada."""
    global _family
    if _family is not None:
        return _family
    _family = FALLBACK
    path = asset_path("fonts/BricolageGrotesque.ttf")
    if path is not None and QFontDatabase.addApplicationFont(str(path)) >= 0:
        _family = FAMILY
    else:
        log.warning("No se pudo cargar %s; usando %s", FAMILY, FALLBACK)
    return _family


def ui_font(point_size: float, weight: QFont.Weight = QFont.Normal) -> QFont:
    font = QFont(load())
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font
