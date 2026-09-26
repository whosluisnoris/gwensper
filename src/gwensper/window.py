"""Ventana principal: configuración del dictado y gestor de modelos.

Línea visual Gwen: tinta, porcelana, azul, niebla e hilo dorado. La costura aparece solo
en tres lugares: la sección activa, la tarjeta del modelo en uso y el progreso de descarga.
"""
from __future__ import annotations

import shutil
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from . import __version__, models
from .audio import list_input_devices
from .config import DEFAULT_MODEL
from .fonts import ui_font
from .icon import GWEN_BLUE, INK_BOTTOM, INK_TOP, MIST, PORCELAIN, app_icon, render

if TYPE_CHECKING:
    from .app import Controller

GOLD = QColor("#E4C57A")
MUTED = "#AEB6D6"
REPO_URL = "https://github.com/whosluisnoris/gwensper"

LANGUAGES = [
    ("", "Detectar automáticamente"), ("es", "Español"), ("en", "Inglés"), ("pt", "Portugués"),
    ("fr", "Francés"), ("it", "Italiano"), ("de", "Alemán"), ("ca", "Catalán"),
    ("nl", "Neerlandés"), ("ru", "Ruso"), ("ja", "Japonés"), ("zh", "Chino"), ("ko", "Coreano"),
]
DEVICES = [("auto", "Automático: GPU si hay, si no CPU"), ("cpu", "Solo CPU"), ("cuda", "GPU NVIDIA")]

STYLE = f"""
QWidget {{ color: {PORCELAIN.name()}; }}
#root {{ background: {INK_BOTTOM.name()}; }}
#sidebar {{ background: #151A34; }}
#content {{ background: {INK_TOP.name()}; }}
QScrollArea, #page {{ background: transparent; border: none; }}
QLabel#muted {{ color: {MUTED}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: #1A1F3D; border: 1px solid #3A4478; border-radius: 8px;
    padding: 6px 10px; min-height: 20px; selection-background-color: {GWEN_BLUE.name()};
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border-color: {GWEN_BLUE.name()}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: #1A1F3D; border: 1px solid #3A4478; selection-background-color: #2E3870; outline: none;
}}
QPushButton {{
    background: transparent; border: 1px solid #3A4478; border-radius: 8px; padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {GWEN_BLUE.name()}; }}
QPushButton:disabled {{ color: #5E6690; border-color: #2B3360; }}
QPushButton#primary {{ background: {GWEN_BLUE.name()}; color: {INK_BOTTOM.name()}; border: none; }}
QPushButton#primary:hover {{ background: #9CC4F8; }}
QPushButton#danger:hover {{ border-color: #E8798E; color: #F2A7B5; }}
QPushButton#link {{ border: none; padding: 2px 0; color: {GWEN_BLUE.name()}; text-align: left; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3A4478;
    background: #1A1F3D; }}
QCheckBox::indicator:checked {{ background: {GWEN_BLUE.name()}; border-color: {GWEN_BLUE.name()}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #3A4478; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def _label(text: str, size: float = 10, weight=QFont.Normal, muted: bool = False, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(ui_font(size, weight))
    if muted:
        lbl.setObjectName("muted")
    lbl.setWordWrap(wrap)
    return lbl


def _combo(items, current) -> QComboBox:
    box = QComboBox()
    for value, label in items:
        box.addItem(label, value)
    box.setCurrentIndex(max(0, box.findData(current)))
    box.setMinimumWidth(240)
    return box


def _format_mb(mb: int) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1000 else f"{mb} MB"


# ---------- piezas con la costura ----------
class Panel(QFrame):
    """Panel plano con borde tenue; `stitched` lo convierte en un parche cosido."""

    def __init__(self, stitched: bool = False):
        super().__init__()
        self.stitched = stitched
        self.setAttribute(Qt.WA_StyledBackground, False)

    def set_stitched(self, stitched: bool) -> None:
        self.stitched = stitched
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, QColor(255, 255, 255, 10))
        border = QColor(GWEN_BLUE)
        border.setAlpha(45)
        p.setPen(QPen(border, 1))
        p.drawPath(path)
        if self.stitched:
            stitch = QPen(MIST, 1.5, Qt.CustomDashLine, Qt.RoundCap)
            stitch.setDashPattern([3.0, 2.8])
            p.setPen(stitch)
            inner = QPainterPath()
            inner.addRoundedRect(r.adjusted(5, 5, -5, -5), 8, 8)
            p.drawPath(inner)


class ThreadProgress(QWidget):
    """Barra de progreso como hilo dorado que se cose de izquierda a derecha."""

    def __init__(self):
        super().__init__()
        self.value = 0
        self.setFixedHeight(8)

    def set_value(self, value: int) -> None:
        self.value = value
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = self.height() / 2
        track = QPen(QColor(255, 255, 255, 50), 1.6, Qt.CustomDashLine, Qt.RoundCap)
        track.setDashPattern([3.0, 2.8])
        p.setPen(track)
        p.drawLine(2, y, self.width() - 2, y)
        if self.value > 0:
            gold = QPen(GOLD, 2.2, Qt.CustomDashLine, Qt.RoundCap)
            gold.setDashPattern([3.0, 2.2])
            p.setPen(gold)
            p.drawLine(2, y, 2 + (self.width() - 4) * min(self.value, 100) / 100, y)


class PrecisionMarks(QWidget):
    """Precisión 1-5 como puntadas cortas encendidas en color niebla."""

    def __init__(self, level: int):
        super().__init__()
        self.level = level
        self.setFixedSize(48, 16)
        self.setToolTip(f"Precisión: {level} de 5")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i in range(5):
            on = i < self.level
            color = QColor(MIST) if on else QColor(255, 255, 255, 45)
            p.setPen(QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap))
            x = 4 + i * 9
            p.drawLine(x, 4, x + 4, 12)


class NavButton(QAbstractButton):
    """Sección de la barra lateral; la activa se marca con una puntada vertical."""

    def __init__(self, text: str):
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(ui_font(11, QFont.Medium))
        self.setFixedHeight(40)

    def sizeHint(self):
        return QSize(180, 40)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(10, 2, -10, -2)
        if self.isChecked() or self.underMouse():
            bg = QPainterPath()
            bg.addRoundedRect(r, 8, 8)
            p.fillPath(bg, QColor(127, 179, 245, 38 if self.isChecked() else 18))
        if self.isChecked():
            stitch = QPen(MIST, 2, Qt.CustomDashLine, Qt.RoundCap)
            stitch.setDashPattern([2.0, 2.2])
            p.setPen(stitch)
            p.drawLine(int(r.left()) + 8, int(r.top()) + 9, int(r.left()) + 8, int(r.bottom()) - 9)
        p.setPen(PORCELAIN if self.isChecked() else QColor(MUTED))
        p.setFont(self.font())
        p.drawText(r.adjusted(22, 0, 0, 0), Qt.AlignVCenter, self.text())

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class HotkeyEdit(QLineEdit):
    """Haz clic y presiona la combinación: se guarda como 'ctrl+alt+d'."""

    hotkey_changed = Signal(str)

    def __init__(self, spec: str):
        super().__init__()
        self.spec = spec
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self._show(spec)

    def _show(self, spec: str) -> None:
        self.setText("+".join(p.capitalize() if len(p) > 1 else p.upper() for p in spec.split("+")))

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.setText("Presiona la combinación…")

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._show(self.spec)

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key_Escape:
            self.clearFocus()
            return
        if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr):
            return
        mods = []
        m = e.modifiers()
        if m & Qt.ControlModifier:
            mods.append("ctrl")
        if m & Qt.AltModifier:
            mods.append("alt")
        if m & Qt.ShiftModifier:
            mods.append("shift")
        if m & Qt.MetaModifier:
            mods.append("win")
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            name = f"f{key - Qt.Key_F1 + 1}"
        elif key == Qt.Key_Space:
            name = "space"
        else:
            name = QKeySequence(key).toString().lower()
            if len(name) != 1 or not name.isalnum():
                return
        if not mods and not name.startswith("f"):
            self.setText("Usa Ctrl, Alt o Shift con una letra")
            return
        self.spec = "+".join(mods + [name])
        self.hotkey_changed.emit(self.spec)
        self.clearFocus()


def _row(title: str, hint: str, control: QWidget) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(18, 12, 18, 12)
    lay.setSpacing(24)
    text = QVBoxLayout()
    text.setSpacing(2)
    text.addWidget(_label(title, 10.5, QFont.Medium))
    if hint:
        text.addWidget(_label(hint, 9, muted=True, wrap=True))
    lay.addLayout(text, 1)
    lay.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
    return row


def _section(title: str, rows: list[QWidget]) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(_label(title, 10, QFont.DemiBold, muted=True))
    panel = Panel()
    inner = QVBoxLayout(panel)
    inner.setContentsMargins(0, 4, 0, 4)
    inner.setSpacing(0)
    for i, r in enumerate(rows):
        if i:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet("background: rgba(127,179,245,0.10); margin: 0 18px;")
            inner.addWidget(line)
        inner.addWidget(r)
    lay.addWidget(panel)
    return box


def _page(title: str, subtitle: str) -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    page = QWidget()
    page.setObjectName("page")
    lay = QVBoxLayout(page)
    lay.setContentsMargins(36, 32, 36, 32)
    lay.setSpacing(22)
    head = QVBoxLayout()
    head.setSpacing(4)
    head.addWidget(_label(title, 20, QFont.DemiBold))
    head.addWidget(_label(subtitle, 10, muted=True, wrap=True))
    lay.addLayout(head)
    scroll.setWidget(page)
    return scroll, lay


# ---------- secciones ----------
class DictationPage(QWidget):
    def __init__(self, ctrl: Controller):
        super().__init__()
        self.ctrl = ctrl
        cfg = ctrl.cfg
        scroll, lay = _page("Dictado", "Cómo escuchas y cómo se escribe lo que dices. Los cambios se guardan solos.")

        self.hotkey = HotkeyEdit(cfg.hotkey)
        self.hotkey.setMinimumWidth(240)
        self.hotkey.hotkey_changed.connect(lambda v: ctrl.apply_changes(hotkey=v))
        mics = list_input_devices()
        if cfg.input_device and cfg.input_device not in mics:
            mics.append(cfg.input_device)
        self.mic = _combo([("", "Predeterminado del sistema")] + [(m, m) for m in mics], cfg.input_device)
        self.mic.currentIndexChanged.connect(lambda: ctrl.apply_changes(input_device=self.mic.currentData()))
        self.language = _combo(LANGUAGES, cfg.language)
        self.language.currentIndexChanged.connect(lambda: ctrl.apply_changes(language=self.language.currentData()))
        lay.addWidget(_section("Atajo y micrófono", [
            _row("Atajo para dictar", "Haz clic y presiona la combinación. Enciende y apaga el dictado.", self.hotkey),
            _row("Micrófono", "", self.mic),
            _row("Idioma", "Elegirlo es más preciso que detectarlo.", self.language),
        ]))

        self.live = _combo([("auto", "Automático"), ("on", "Mientras hablo"), ("off", "Al terminar cada frase")],
                           cfg.live_mode)
        self.live.currentIndexChanged.connect(lambda: ctrl.apply_changes(live_mode=self.live.currentData()))
        self.insert = _combo([("type", "Teclear palabra por palabra"), ("paste", "Pegar la frase completa")],
                             cfg.insert_mode)
        self.insert.currentIndexChanged.connect(lambda: ctrl.apply_changes(insert_mode=self.insert.currentData()))
        lay.addWidget(_section("Escritura", [
            _row("Cuándo escribir", "Mientras hablas el texto va 1 o 2 s detrás de tu voz. Automático lo "
                 "activa solo con GPU.", self.live),
            _row("Cómo escribir", "Pegar usa Ctrl+V y después devuelve lo que tenías en el portapapeles.",
                 self.insert),
        ]))

        self.silence = QSpinBox(minimum=250, maximum=3000, singleStep=50, suffix=" ms")
        self.silence.setValue(cfg.silence_ms)
        self.silence.valueChanged.connect(lambda v: ctrl.apply_changes(silence_ms=v))
        self.sensitivity = QDoubleSpinBox(minimum=1.5, maximum=10.0, singleStep=0.5, decimals=1)
        self.sensitivity.setValue(cfg.sensitivity)
        self.sensitivity.valueChanged.connect(lambda v: ctrl.apply_changes(sensitivity=v))
        for w in (self.silence, self.sensitivity):
            w.setMinimumWidth(120)
        lay.addWidget(_section("Detección de voz", [
            _row("Pausa que cierra una frase", "Súbela si te corta a mitad de una idea.", self.silence),
            _row("Umbral de voz", "Súbelo si se transcribe el ruido de fondo.", self.sensitivity),
        ]))

        self.always = QCheckBox()
        self.always.setChecked(cfg.overlay_always)
        self.always.toggled.connect(ctrl.set_overlay_always)
        self.autostart = QCheckBox()
        self.autostart.setChecked(ctrl.autostart_enabled())
        self.autostart.toggled.connect(ctrl.set_autostart)
        lay.addWidget(_section("Indicador y arranque", [
            _row("Mostrar siempre el indicador", "Si no, solo aparece mientras dictas.", self.always),
            _row("Iniciar con Windows", "Gwensper arranca en segundo plano, en la bandeja.", self.autostart),
        ]))
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def sync(self) -> None:
        self.always.blockSignals(True)
        self.always.setChecked(self.ctrl.cfg.overlay_always)
        self.always.blockSignals(False)
        self.autostart.blockSignals(True)
        self.autostart.setChecked(self.ctrl.autostart_enabled())
        self.autostart.blockSignals(False)


class ModelCard(Panel):
    def __init__(self, info: models.ModelInfo, page: ModelsPage):
        super().__init__()
        self.info = info
        self.page = page
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(_label(info.title, 12.5, QFont.DemiBold))
        self.badge = _label("", 9, QFont.Medium)
        head.addWidget(self.badge)
        head.addStretch(1)
        text.addLayout(head)
        text.addWidget(_label(info.description, 9.5, muted=True, wrap=True))
        top.addLayout(text, 1)

        self.btn_use = QPushButton("Usar")
        self.btn_use.setObjectName("primary")
        self.btn_use.clicked.connect(lambda: page.ctrl.use_model(info.name))
        self.btn_download = QPushButton("Descargar")
        self.btn_download.setObjectName("primary")
        self.btn_download.clicked.connect(lambda: page.ctrl.download_model(info.name))
        self.btn_delete = QPushButton("Eliminar")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(lambda: page.ctrl.delete_model(info.name))
        for b in (self.btn_download, self.btn_use, self.btn_delete):
            b.setCursor(Qt.PointingHandCursor)
            top.addWidget(b, 0, Qt.AlignTop)
        lay.addLayout(top)

        facts = QHBoxLayout()
        facts.setSpacing(12)
        self.size_label = _label("", 9.5)
        for caption, widget in (
            ("Tamaño", self.size_label),
            ("En CPU", _label(info.cpu_speed, 9.5)),
            ("En GPU", _label(info.gpu_speed, 9.5)),
            ("Precisión", PrecisionMarks(info.precision)),
        ):
            col_widget = QWidget()
            col_widget.setFixedWidth(96)  # columnas alineadas entre tarjetas
            col = QVBoxLayout(col_widget)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)
            col.addWidget(_label(caption, 8.5, muted=True))
            col.addWidget(widget)
            facts.addWidget(col_widget)
        facts.addStretch(1)
        lay.addLayout(facts)

        self.progress = ThreadProgress()
        self.progress.hide()
        lay.addWidget(self.progress)

    def refresh(self, downloaded: bool, size_mb: int, in_use: bool, downloading: int | None, busy: bool) -> None:
        self.set_stitched(in_use)
        if in_use:
            self.badge.setText("En uso")
            self.badge.setStyleSheet(f"color: {MIST.name()};")
        elif downloaded:
            self.badge.setText("Descargado")
            self.badge.setStyleSheet(f"color: {MUTED};")
        else:
            self.badge.setText("")
        self.size_label.setText(_format_mb(size_mb if downloaded and size_mb else self.info.size_mb))
        is_downloading = downloading is not None
        self.progress.setVisible(is_downloading)
        if is_downloading:
            self.progress.set_value(max(0, downloading))
            self.badge.setText(f"Descargando {downloading} %" if downloading >= 0 else "Descargando")
            self.badge.setStyleSheet(f"color: {GOLD.name()};")
        self.btn_download.setVisible(not downloaded and not is_downloading)
        self.btn_download.setEnabled(not busy)
        self.btn_use.setVisible(downloaded and not in_use)
        self.btn_use.setEnabled(not busy)
        self.btn_delete.setVisible(downloaded and not in_use)
        self.btn_delete.setEnabled(not busy)


class ModelsPage(QWidget):
    def __init__(self, ctrl: Controller):
        super().__init__()
        self.ctrl = ctrl
        scroll, lay = _page(
            "Modelos",
            "Los modelos más grandes entienden mejor, pero ocupan más espacio y necesitan más potencia. "
            "Todo corre en tu computadora.",
        )

        self.device = _combo(DEVICES, ctrl.cfg.device)
        self.device.currentIndexChanged.connect(lambda: ctrl.apply_changes(device=self.device.currentData()))
        self.now = _label("", 10.5, QFont.Medium)
        self.disk = _label("", 9, muted=True)
        now_box = QVBoxLayout()
        now_box.setSpacing(2)
        now_box.addWidget(self.now)
        now_box.addWidget(self.disk)
        now_widget = QWidget()
        now_widget.setLayout(now_box)
        self.auto_link = QPushButton()
        self.auto_link.setObjectName("link")
        self.auto_link.setCursor(Qt.PointingHandCursor)
        self.auto_link.clicked.connect(lambda: ctrl.use_model(""))
        lay.addWidget(_section("Motor", [
            _row("Procesar con", "Con una GPU NVIDIA el dictado es varias veces más rápido.", self.device),
            _row("Ahora", "", now_widget),
            _row("Elección del modelo", "", self.auto_link),
        ]))

        lay.addWidget(_label("Modelos disponibles", 10, QFont.DemiBold, muted=True))
        self.cards = [ModelCard(info, self) for info in models.CATALOG]
        for card in self.cards:
            lay.addWidget(card)
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self) -> None:
        ctrl = self.ctrl
        t = ctrl.transcriber
        if ctrl.ready and t.model_name:
            where = "GPU NVIDIA" if t.device == "cuda" else "CPU"
            self.now.setText(f"{t.model_name} en {where}")
        else:
            self.now.setText("Cargando el modelo…")
        try:
            free = shutil.disk_usage(Path.home().anchor).free // (1024 ** 3)
            self.disk.setText(f"{free} GB libres en el disco")
        except OSError:
            self.disk.setText("")
        if ctrl.cfg.model:
            self.auto_link.setText("Volver a elegir automáticamente")
            self.auto_link.setEnabled(True)
        else:
            self.auto_link.setText(
                f"Automática: {DEFAULT_MODEL['cpu']} en CPU, {DEFAULT_MODEL['cuda']} en GPU")
            self.auto_link.setEnabled(False)
        busy = bool(ctrl.downloads) or not ctrl.ready
        for card in self.cards:
            name = card.info.name
            downloaded = models.is_downloaded(name)
            card.refresh(
                downloaded=downloaded,
                size_mb=models.disk_size_mb(name) if downloaded else 0,
                in_use=ctrl.ready and t.model_name == name,
                downloading=ctrl.downloads.get(name),
                busy=busy,
            )

    def update_progress(self, name: str, pct: int) -> None:
        for card in self.cards:
            if card.info.name == name:
                card.progress.set_value(max(0, pct))
                card.badge.setText(f"Descargando {pct} %" if pct >= 0 else "Descargando")


class AboutPage(QWidget):
    def __init__(self, ctrl: Controller):
        super().__init__()
        scroll, lay = _page("Acerca de", f"Gwensper {__version__}")
        icon = QLabel()
        icon.setPixmap(render(192).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(icon)
        lay.addWidget(_label(
            "Dictado por voz para Windows con Whisper. Presiona el atajo, habla, y lo que dices se escribe "
            "en la app donde tengas el cursor. El audio nunca sale de tu computadora.", 10.5, wrap=True))
        buttons = QHBoxLayout()
        gh = QPushButton("Ver el proyecto en GitHub")
        gh.setObjectName("primary")
        gh.clicked.connect(lambda: webbrowser.open(REPO_URL))
        folder = QPushButton("Abrir carpeta de configuración")
        folder.clicked.connect(ctrl.open_data_dir)
        for b in (gh, folder):
            b.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        lay.addWidget(_label(
            "Transcripción con faster-whisper, basado en Whisper de OpenAI. Fuente Bricolage Grotesque "
            "(SIL Open Font License). La estética es un homenaje de fan a Gwen, de League of Legends; "
            "Gwensper no está afiliado ni respaldado por Riot Games.", 9, muted=True, wrap=True))
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


# ---------- ventana ----------
class MainWindow(QWidget):
    PAGES = ("dictado", "modelos", "acerca")

    def __init__(self, ctrl: Controller):
        super().__init__()
        self.ctrl = ctrl
        self.setObjectName("root")
        self.setWindowTitle("Gwensper")
        self.setWindowIcon(app_icon())
        self.resize(900, 640)
        self.setMinimumSize(760, 520)
        self.setFont(ui_font(10))
        self.setStyleSheet(STYLE)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 22, 0, 18)
        side.setSpacing(4)
        brand = QHBoxLayout()
        brand.setContentsMargins(20, 0, 20, 18)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(render(64).scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        brand.addWidget(_label("Gwensper", 15, QFont.DemiBold))
        brand.addStretch(1)
        side.addLayout(brand)

        self.nav = []
        for key, title in zip(self.PAGES, ("Dictado", "Modelos", "Acerca de")):
            b = NavButton(title)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            side.addWidget(b)
            self.nav.append(b)
        side.addStretch(1)

        status = QVBoxLayout()
        status.setContentsMargins(22, 0, 18, 0)
        status.setSpacing(2)
        self.status_model = _label("", 9.5, QFont.Medium)
        self.status_where = _label("", 9, muted=True)
        self.status_hotkey = _label("", 9, muted=True, wrap=True)
        status.addWidget(self.status_model)
        status.addWidget(self.status_where)
        status.addSpacing(10)
        status.addWidget(self.status_hotkey)
        side.addLayout(status)

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.dictation = DictationPage(ctrl)
        self.models = ModelsPage(ctrl)
        self.about = AboutPage(ctrl)
        for w in (self.dictation, self.models, self.about):
            self.stack.addWidget(w)
        content = QWidget()
        content.setObjectName("content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.stack)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(sidebar)
        root.addWidget(content, 1)
        self.show_page("dictado")
        self.refresh()

    def show_page(self, key: str) -> None:
        idx = self.PAGES.index(key) if key in self.PAGES else 0
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav):
            b.setChecked(i == idx)
        if key == "modelos":
            self.models.refresh()

    def refresh(self) -> None:
        ctrl = self.ctrl
        t = ctrl.transcriber
        if ctrl.ready and t.model_name:
            self.status_model.setText(t.model_name)
            self.status_where.setText("en GPU NVIDIA" if t.device == "cuda" else "en CPU")
        else:
            self.status_model.setText("Preparando el modelo")
            self.status_where.setText(ctrl.status_text)
        self.status_hotkey.setText(f"Presiona {ctrl.hotkey_label()} en cualquier app para dictar.")
        self.dictation.sync()
        if self.stack.currentWidget() is self.models:
            self.models.refresh()

    def closeEvent(self, e):
        # Cerrar solo oculta: Gwensper sigue en la bandeja.
        e.ignore()
        self.hide()
        self.ctrl.window_closed()

