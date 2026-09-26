"""Fuentes de audio: micrófono real o un archivo (para pruebas)."""
from __future__ import annotations

import logging
import queue
import threading
import time

import numpy as np

from .segmenter import FRAME_LEN, FRAME_MS, SAMPLE_RATE

log = logging.getLogger(__name__)


def list_input_devices() -> list[str]:
    import sounddevice as sd

    try:
        default_api = sd.default.hostapi
        return [
            d["name"]
            for d in sd.query_devices()
            if d["max_input_channels"] > 0 and d["hostapi"] == default_api
        ]
    except Exception:  # noqa: BLE001
        log.exception("No se pudieron listar micrófonos")
        return []


def _resample(x: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return x
    n = int(round(len(x) * dst_rate / src_rate))
    return np.interp(np.linspace(0, len(x), n, endpoint=False), np.arange(len(x)), x).astype(np.float32)


class Microphone:
    """Entrega frames de 30 ms a 16 kHz mono en `self.frames` (una Queue)."""

    def __init__(self, device_name: str = ""):
        self.device_name = device_name
        self.frames: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = None
        self._buffer = np.zeros(0, dtype=np.float32)
        self._rate = SAMPLE_RATE

    def _device_index(self):
        if not self.device_name:
            return None
        import sounddevice as sd

        for i, d in enumerate(sd.query_devices()):
            if d["name"] == self.device_name and d["max_input_channels"] > 0:
                return i
        log.warning("Micrófono '%s' no encontrado; usando el predeterminado", self.device_name)
        return None

    def _callback(self, indata, _frames, _time, status):
        if status:
            log.debug("audio: %s", status)
        mono = indata[:, 0].astype(np.float32, copy=True)
        mono = _resample(mono, self._rate, SAMPLE_RATE)
        buf = np.concatenate((self._buffer, mono))
        n = len(buf) // FRAME_LEN
        for i in range(n):
            self.frames.put(buf[i * FRAME_LEN:(i + 1) * FRAME_LEN])
        self._buffer = buf[n * FRAME_LEN:]

    def start(self) -> None:
        import sounddevice as sd

        device = self._device_index()
        try:
            self._rate = SAMPLE_RATE
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=FRAME_LEN, device=device, callback=self._callback,
            )
        except Exception:  # noqa: BLE001 - el dispositivo no acepta 16 kHz
            info = sd.query_devices(device, "input")
            self._rate = int(info["default_samplerate"])
            log.info("Micrófono a %d Hz (re-muestreo a 16 kHz)", self._rate)
            self._stream = sd.InputStream(
                samplerate=self._rate, channels=1, dtype="float32",
                blocksize=self._rate * FRAME_MS // 1000, device=device, callback=self._callback,
            )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        self._buffer = np.zeros(0, dtype=np.float32)


class FileSource:
    """Reproduce un archivo de audio como si fuera el micrófono, en tiempo real."""

    def __init__(self, path: str):
        from faster_whisper import decode_audio

        self.audio = decode_audio(path, sampling_rate=SAMPLE_RATE)
        # Silencio al final para que se cierre la última frase.
        self.audio = np.concatenate((self.audio, np.zeros(SAMPLE_RATE * 2, dtype=np.float32)))
        self.frames: queue.Queue[np.ndarray] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        t0 = time.perf_counter()
        for i in range(len(self.audio) // FRAME_LEN):
            if self._stop.is_set():
                return
            self.frames.put(self.audio[i * FRAME_LEN:(i + 1) * FRAME_LEN])
            delay = t0 + (i + 1) * FRAME_MS / 1000 - time.perf_counter()
            if delay > 0:
                time.sleep(delay)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def finished(self) -> bool:
        return self._thread is not None and not self._thread.is_alive()
