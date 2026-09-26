"""Corta el audio continuo del micrófono en frases usando energía y pausas.

Lógica pura (sin E/S) para poder probarla con audio sintético.
"""
from __future__ import annotations

from collections import deque

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_LEN = SAMPLE_RATE * FRAME_MS // 1000


def rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(frame), dtype=np.float64))) if frame.size else 0.0


class Segmenter:
    def __init__(
        self,
        silence_ms: int = 600,
        max_phrase_s: float = 20.0,
        sensitivity: float = 3.0,
        min_speech_ms: int = 240,
        pre_roll_ms: int = 300,
        min_threshold: float = 0.006,
        frame_ms: int = FRAME_MS,
    ):
        self.frame_ms = frame_ms
        self.silence_frames = max(1, silence_ms // frame_ms)
        self.max_frames = max(1, int(max_phrase_s * 1000 / frame_ms))
        self.min_speech_frames = max(1, min_speech_ms // frame_ms)
        self.sensitivity = sensitivity
        self.min_threshold = min_threshold

        self.noise: float | None = None
        self.level = 0.0  # 0..1 para la interfaz
        self._pre_roll: deque[np.ndarray] = deque(maxlen=max(1, pre_roll_ms // frame_ms))
        self._reset_phrase()

    def _reset_phrase(self) -> None:
        self.in_speech = False
        self._frames: list[np.ndarray] = []
        self._rms: list[float] = []
        self._voiced = 0
        self._silent_run = 0
        self._onset = 0

    @property
    def threshold(self) -> float:
        return max(self.min_threshold, (self.noise or 0.0) * self.sensitivity)

    def feed(self, frame: np.ndarray) -> list[np.ndarray]:
        """Procesa un frame; devuelve las frases completadas (normalmente 0 o 1)."""
        e = rms(frame)
        if self.noise is None:
            # Acotado por si el dictado empieza mientras ya estás hablando.
            self.noise = min(e, 0.01)
        self.level = min(1.0, e / (self.threshold * 4)) if self.threshold else 0.0
        voiced = e > self.threshold
        out: list[np.ndarray] = []

        if not self.in_speech:
            self._pre_roll.append(frame)
            if voiced:
                self._onset += 1
            else:
                self._onset = 0
                # El ruido de fondo se adapta solo durante el silencio.
                self.noise = 0.95 * self.noise + 0.05 * e
            if self._onset >= 2:
                # Inicio de frase: incluye el pre-roll (y el frame actual).
                self.in_speech = True
                self._frames = list(self._pre_roll)
                self._rms = [rms(f) for f in self._frames]
                self._voiced = self._onset
                self._pre_roll.clear()
            return out

        self._frames.append(frame)
        self._rms.append(e)
        if voiced:
            self._voiced += 1
            self._silent_run = 0
        else:
            self._silent_run += 1

        if self._silent_run >= self.silence_frames:
            out.extend(self._emit())
        elif len(self._frames) >= self.max_frames:
            # Frase demasiado larga: corta. Si fue por un ruido de fondo que subió, el umbral
            # se recalibra de a poco (como mucho hasta el umbral actual) para no tapar la voz.
            self.noise = max(self.noise, min(float(np.percentile(self._rms, 10)), self.threshold))
            out.extend(self._emit())
        return out

    def _emit(self) -> list[np.ndarray]:
        frames, voiced = self._frames, self._voiced
        # Conserva ~200 ms de la cola de silencio y descarta el resto.
        keep_tail = max(0, self._silent_run - 200 // self.frame_ms)
        if keep_tail:
            frames = frames[:-keep_tail]
        self._reset_phrase()
        if voiced < self.min_speech_frames or not frames:
            return []
        return [np.concatenate(frames).astype(np.float32, copy=False)]

    def flush(self) -> np.ndarray | None:
        """Cierra la frase en curso (al apagar el dictado)."""
        if not self.in_speech:
            self._pre_roll.clear()
            return None
        phrases = self._emit()
        return phrases[0] if phrases else None
