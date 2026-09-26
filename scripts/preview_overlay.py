"""Genera docs/estados.png con todos los estados del indicador flotante."""
import sys
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(out: Path) -> None:
    app = QApplication([])  # noqa: F841 - necesario para dibujar widgets
    from gwensper import fonts
    from gwensper.overlay import Overlay

    fonts.load()

    def snap(fn):
        o = Overlay()
        o.animate = True
        fn(o)
        for _ in range(12):
            o._tick()
        return o.grab()

    states = [
        ("Listo", lambda o: o.set_state("idle", "Ctrl+Alt+D para dictar")),
        ("Escuchando", lambda o: (o.set_state("listening", "Escuchando"), setattr(o, "level", 0.8))),
        ("Escribiendo lo dictado", lambda o: (o.set_state("listening", "Escuchando"),
                                              setattr(o, "level", 0.3), o.set_busy(True))),
        ("Descargando el modelo", lambda o: (o.set_state("loading", ""), o.set_progress(62))),
        ("Error", lambda o: o.set_state("error", "Micrófono no disponible")),
    ]
    shots = [(label, snap(fn)) for label, fn in states]
    row_h, label_w, pad = 72, 200, 24
    width = label_w + max(int(s.width() / s.devicePixelRatio()) for _, s in shots) + pad * 2
    height = row_h * len(shots) + pad * 2
    out_pm = QPixmap(width * 2, height * 2)
    out_pm.fill(QColor("#141833"))
    p = QPainter(out_pm)
    p.scale(2, 2)
    p.setRenderHint(QPainter.Antialiasing)
    p.setFont(fonts.ui_font(11))
    for i, (label, shot) in enumerate(shots):
        y = pad + i * row_h
        p.setPen(QColor("#AEB6D6"))
        p.drawText(QPointF(pad, y + 31), label)
        p.drawPixmap(pad + label_w, y, shot)
    p.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    out_pm.save(str(out))
    print("Guardado", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "estados.png")
