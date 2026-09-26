"""Controlador principal: une micrófono, segmentador, Whisper, escritura e interfaz."""
from __future__ import annotations

import getpass
import logging
import os
import queue
import sys
import threading

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import APP_NAME, fonts, postprocess, shortcuts, winapi
from .audio import FileSource, Microphone
from .config import Config, data_dir
from .hotkey import GlobalHotkey
from .icon import app_icon
from .overlay import Overlay
from .segmenter import Segmenter
from .settings import SettingsDialog
from .transcriber import Transcriber
from .tray import Tray
from .typer import Typer

log = logging.getLogger(__name__)

SERVER_NAME = f"gwensper-{getpass.getuser()}"
CONTEXT_CHARS = 200


class Signals(QObject):
    """Puente thread-safe desde los hilos de trabajo hacia la interfaz."""
    status = Signal(str)
    progress = Signal(int)
    model_loaded = Signal(bool, str)
    level = Signal(float)
    busy = Signal(bool)
    text = Signal(str)
    source_finished = Signal()


class Controller(QObject):
    def __init__(self, cfg: Config, test_audio: str | None = None):
        super().__init__()
        self.cfg = cfg
        self.test_audio = test_audio
        self.sig = Signals()
        self.transcriber = Transcriber(cfg)
        self.typer = Typer(cfg.insert_mode)
        self.model_lock = threading.Lock()
        self.phrases: queue.Queue[np.ndarray] = queue.Queue()

        self.ready = False
        self.listening = False
        self.pending_start = False
        self.context = ""
        self.source = None
        self.segmenter: Segmenter | None = None
        self._audio_thread: threading.Thread | None = None
        self._stop_audio = threading.Event()

        # Interfaz
        self.overlay = Overlay()
        self.overlay.clicked.connect(self.toggle)
        self.overlay.moved.connect(self._save_overlay_pos)
        self.overlay.context_requested.connect(lambda pos: self.tray.menu.popup(pos))
        self.overlay.place(cfg.overlay_x, cfg.overlay_y)
        self.tray = Tray(self._hotkey_label(), cfg.overlay_always, shortcuts.autostart_enabled())
        self.tray.toggle_requested.connect(self.toggle)
        self.tray.settings_requested.connect(self.open_settings)
        self.tray.overlay_toggled.connect(self._set_overlay_always)
        self.tray.autostart_toggled.connect(self._set_autostart)
        self.tray.open_folder_requested.connect(self._open_data_dir)
        self.tray.quit_requested.connect(self.quit)
        self.tray.show()
        if cfg.overlay_always:
            self.overlay.show()
        self._flash_timer = QTimer(self, singleShot=True, timeout=self._hide_if_inactive)
        self._finish_timer = QTimer(self, interval=150, timeout=self._check_finished)

        self.hotkey = GlobalHotkey(lambda: QTimer.singleShot(0, self.toggle))
        self._register_hotkey(notify=True)

        # Señales de los hilos
        self.sig.status.connect(self._on_status)
        self.sig.progress.connect(self.overlay.set_progress)
        self.sig.model_loaded.connect(self._on_model_loaded)
        self.sig.level.connect(self.overlay.set_level)
        self.sig.busy.connect(self.overlay.set_busy)
        self.sig.text.connect(self._insert_text, Qt.QueuedConnection)
        self.sig.source_finished.connect(self.stop)

        threading.Thread(target=self._transcribe_loop, daemon=True, name="transcribe").start()
        self.load_model()

    # ---------- modelo ----------
    def load_model(self) -> None:
        self.ready = False
        self.overlay.set_state("loading", "Preparando")
        threading.Thread(target=self._load_worker, daemon=True, name="load-model").start()

    def _load_worker(self) -> None:
        with self.model_lock:
            try:
                self.transcriber.load(on_status=self.sig.status.emit, on_progress=self.sig.progress.emit)
                where = "GPU" if self.transcriber.device == "cuda" else "CPU"
                self.sig.model_loaded.emit(True, f"{self.transcriber.model_name} en {where}")
            except Exception as e:  # noqa: BLE001
                log.exception("Error cargando el modelo")
                self.sig.model_loaded.emit(False, str(e))

    def _on_status(self, text: str) -> None:
        self.tray.set_status(text)
        if not self.ready:
            self.overlay.set_state("loading", text)

    def _on_model_loaded(self, ok: bool, detail: str) -> None:
        self.ready = ok
        if not ok:
            self.pending_start = False
            self.overlay.set_state("error", "No se pudo cargar el modelo")
            self._flash(4000)
            self.tray.set_status(f"Error: {detail}")
            self.tray.showMessage(APP_NAME, f"No se pudo cargar el modelo:\n{detail}", self.tray.icon())
            return
        self.tray.set_status(f"Listo ({detail})")
        self._show_idle()
        if self.pending_start or self.test_audio:
            self.pending_start = False
            self.start()
        else:
            self._hide_if_inactive()

    # ---------- dictado ----------
    def toggle(self) -> None:
        if self.listening:
            self.stop()
        elif self.ready:
            self.start()
        else:
            # El modelo aún carga: la píldora muestra el progreso y el dictado empieza al terminar.
            self.pending_start = not self.pending_start
            if self.pending_start:
                self.overlay.appear()
            else:
                self._hide_if_inactive()

    def start(self) -> None:
        if self.listening or not self.ready:
            return
        cfg = self.cfg
        try:
            source = FileSource(self.test_audio) if self.test_audio else Microphone(cfg.input_device)
            source.start()
        except Exception as e:  # noqa: BLE001
            log.exception("No se pudo abrir el micrófono")
            self.overlay.set_state("error", "Micrófono no disponible")
            self._flash(3000)
            self.tray.showMessage(APP_NAME, f"No se pudo abrir el micrófono:\n{e}", self.tray.icon())
            return
        self.source = source
        self.segmenter = Segmenter(
            silence_ms=cfg.silence_ms, max_phrase_s=cfg.max_phrase_s, sensitivity=cfg.sensitivity
        )
        self.context = ""
        self._stop_audio.clear()
        self._audio_thread = threading.Thread(
            target=self._audio_loop, args=(source, self.segmenter), daemon=True, name="audio"
        )
        self._audio_thread.start()
        self.listening = True
        self._flash_timer.stop()
        self._finish_timer.stop()
        self.overlay.set_state("listening", "Escuchando")
        self.overlay.appear()
        self.tray.set_listening(True)

    def stop(self) -> None:
        if not self.listening:
            return
        self.listening = False
        self._stop_audio.set()
        if self.source is not None:
            self.source.stop()
        if self._audio_thread is not None:
            self._audio_thread.join(timeout=1)
        if self.segmenter is not None:
            tail = self.segmenter.flush()
            if tail is not None:
                self.phrases.put(tail)
        self.source = None
        self.tray.set_listening(False)
        # La píldora sigue visible hasta que se escriba la última frase.
        self.overlay.set_state("idle", "Terminando")
        self._finish_timer.start()
        self._check_finished()
        if self.test_audio:
            # En modo prueba, cierra cuando termine de transcribir.
            QTimer.singleShot(0, self._quit_when_idle)

    def _audio_loop(self, source, segmenter: Segmenter) -> None:
        n = 0
        while not self._stop_audio.is_set():
            try:
                frame = source.frames.get(timeout=0.1)
            except queue.Empty:
                if isinstance(source, FileSource) and source.finished:
                    self.sig.source_finished.emit()
                    return
                continue
            for phrase in segmenter.feed(frame):
                self.phrases.put(phrase)
            n += 1
            if n % 2 == 0:
                self.sig.level.emit(segmenter.level)

    def _transcribe_loop(self) -> None:
        while True:
            audio = self.phrases.get()
            self.sig.busy.emit(True)
            try:
                with self.model_lock:
                    text = self.transcriber.transcribe(audio, prompt=self.context[-CONTEXT_CHARS:])
                text = postprocess.clean(text)
                log.info("Frase (%.1fs): %r", len(audio) / 16000, text)
                if text:
                    self.sig.text.emit(text)
            except Exception:  # noqa: BLE001
                log.exception("Error transcribiendo")
            finally:
                self.phrases.task_done()
                if self.phrases.empty():
                    self.sig.busy.emit(False)

    def _insert_text(self, text: str) -> None:
        piece = postprocess.join(self.context, text)
        # Se encola y se escribe palabra por palabra; el contexto para Whisper se actualiza ya.
        self.typer.insert(piece)
        self.context += piece

    def _show_idle(self) -> None:
        self.overlay.set_state("idle", f"{self._hotkey_label()} para dictar")

    # ---------- visibilidad de la píldora ----------
    def _work_pending(self) -> bool:
        # unfinished_tasks cuenta también la frase que se está transcribiendo ahora.
        return self.phrases.unfinished_tasks > 0 or self.typer.busy

    def _check_finished(self) -> None:
        if self.listening:
            self._finish_timer.stop()
            return
        if self._work_pending():
            return
        self._finish_timer.stop()
        self._show_idle()
        self._hide_if_inactive()

    def _flash(self, ms: int) -> None:
        """Muestra la píldora un momento (errores, avisos) y luego la oculta."""
        self.overlay.appear()
        self._flash_timer.start(ms)

    def _hide_if_inactive(self) -> None:
        if self.listening or self.pending_start or self.cfg.overlay_always:
            return
        if self._flash_timer.isActive() or self._finish_timer.isActive():
            return
        self.overlay.disappear()

    # ---------- configuración ----------
    def _hotkey_label(self) -> str:
        return "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in self.cfg.hotkey.split("+"))

    def _register_hotkey(self, notify: bool) -> None:
        ok = self.hotkey.register(int(self.overlay.winId()), self.cfg.hotkey)
        if not ok and notify:
            self.tray.showMessage(
                APP_NAME,
                f"El atajo {self._hotkey_label()} está en uso por otra app. Cámbialo en Configuración.",
                self.tray.icon(),
            )

    def open_settings(self) -> None:
        status = self.tray.toolTip().replace("Gwensper — ", "Estado: ")
        dlg = SettingsDialog(self.cfg, status)
        dlg.activateWindow()
        if dlg.exec() != SettingsDialog.Accepted:
            return
        new, old = dlg.cfg, self.cfg
        reload_model = (new.model, new.device) != (old.model, old.device)
        restart_audio = self.listening and (
            (new.input_device, new.silence_ms, new.sensitivity) != (old.input_device, old.silence_ms, old.sensitivity)
            or reload_model
        )
        for f in ("hotkey", "language", "device", "model", "input_device", "silence_ms", "sensitivity",
                  "insert_mode"):
            setattr(self.cfg, f, getattr(new, f))
        self.cfg.save()
        self.typer.mode = self.cfg.insert_mode
        self.tray.hotkey_label = self._hotkey_label()
        self.tray.set_listening(self.listening)
        self._register_hotkey(notify=True)
        if restart_audio:
            self.stop()
        if reload_model:
            self.load_model()
        elif restart_audio:
            self.start()
        elif not self.listening and self.ready:
            self._show_idle()

    def _save_overlay_pos(self, x: int, y: int) -> None:
        self.cfg.overlay_x, self.cfg.overlay_y = x, y
        self.cfg.save()

    def _set_overlay_always(self, always: bool) -> None:
        self.cfg.overlay_always = always
        self.cfg.save()
        if always:
            self.overlay.appear()
        else:
            self._hide_if_inactive()

    def _set_autostart(self, enabled: bool) -> None:
        try:
            shortcuts.set_autostart(enabled)
        except Exception as e:  # noqa: BLE001
            log.exception("Autostart")
            self.tray.showMessage(APP_NAME, f"No se pudo cambiar el inicio automático:\n{e}", self.tray.icon())

    def _open_data_dir(self) -> None:
        folder = data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def show_overlay(self) -> None:
        """Otra instancia pidió mostrarse: enseña la píldora un momento."""
        if not self.listening:
            self._flash(2500)

    def _quit_when_idle(self) -> None:
        if not self._work_pending():
            QTimer.singleShot(500, self.quit)
        else:
            QTimer.singleShot(200, self._quit_when_idle)

    def quit(self) -> None:
        self.stop()
        self.hotkey.unregister()
        self.tray.hide()
        QApplication.quit()


def _first_run(ctrl: Controller, cfg: Config) -> None:
    if cfg.first_run_done:
        return
    try:
        shortcuts.install_start_menu()
    except Exception:  # noqa: BLE001
        log.exception("No se pudo crear el acceso directo del menú Inicio")
    cfg.first_run_done = True
    cfg.save()
    ctrl.tray.showMessage(
        APP_NAME,
        f"Gwensper está en la bandeja. Presiona {ctrl._hotkey_label()} para empezar a dictar "
        "y otra vez para detener.",
        ctrl.tray.icon(),
        8000,
    )


def run(test_audio: str | None = None) -> int:
    winapi.set_app_user_model_id("Gwensper.Dictado")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    fonts.load()
    app.setQuitOnLastWindowClosed(False)

    # Instancia única: si ya está abierta, solo muestra el indicador.
    probe = QLocalSocket()
    probe.connectToServer(SERVER_NAME)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "La bandeja del sistema no está disponible.")
        return 1

    cfg = Config.load()
    ctrl = Controller(cfg, test_audio=test_audio)

    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    def on_connection():
        sock = server.nextPendingConnection()
        if sock is not None:
            sock.readyRead.connect(ctrl.show_overlay)
            sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_connection)
    if not test_audio:
        QTimer.singleShot(500, lambda: _first_run(ctrl, cfg))
    return app.exec()
