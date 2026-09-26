"""Regenera src/gwensper/assets/icon.png e icon.ico a partir de gwensper.icon."""
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from gwensper.icon import render

ASSETS = Path(__file__).resolve().parents[1] / "src" / "gwensper" / "assets"

if __name__ == "__main__":
    app = QGuiApplication([])
    ASSETS.mkdir(parents=True, exist_ok=True)
    render(512).save(str(ASSETS / "icon.png"), "PNG")
    render(256).save(str(ASSETS / "icon.ico"), "ICO")
    print("Iconos guardados en", ASSETS)
