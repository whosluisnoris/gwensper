"""Genera capturas de la ventana principal (docs/ventana-*.png) con datos de ejemplo."""
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class FakeController:
    """Lo mínimo que la ventana necesita del controlador, sin cargar Whisper."""

    def __init__(self):
        from gwensper.config import Config

        self.cfg = Config()
        self.transcriber = SimpleNamespace(model_name="large-v3-turbo", device="cuda")
        self.ready = True
        self.status_text = ""
        self.downloads = {"medium": 45}

    def hotkey_label(self):
        return "Ctrl+Alt+D"

    def autostart_enabled(self):
        return False

    def __getattr__(self, _name):  # apply_changes, use_model, etc.: sin efecto en la captura
        return lambda *a, **k: None


def main(out_dir: Path) -> None:
    app = QApplication([])
    from gwensper import fonts
    from gwensper.window import MainWindow

    fonts.load()
    win = MainWindow(FakeController())
    win.resize(900, 640)
    out_dir.mkdir(parents=True, exist_ok=True)
    for page in MainWindow.PAGES:
        win.show_page(page)
        win.show()
        app.processEvents()
        win.grab().save(str(out_dir / f"ventana-{page}.png"))
        print("Guardado", out_dir / f"ventana-{page}.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs")
