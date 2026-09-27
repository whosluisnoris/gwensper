"""Carga de faster-whisper (GPU si se puede, si no CPU) y transcripción de frases."""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from . import cuda_dlls
from .config import COMPUTE_TYPE, Config
from .streaming import Word

log = logging.getLogger(__name__)

ALLOW_PATTERNS = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]

StatusFn = Callable[[str], None]
ProgressFn = Callable[[int], None]  # 0..100, -1 = indeterminado


def repo_id(model: str) -> str:
    from faster_whisper.utils import _MODELS

    return model if "/" in model else _MODELS.get(model, model)


def _folder_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            path = os.path.join(root, f)
            # Solo archivos reales: los enlaces apuntan a blobs ya contados (o compartidos).
            if os.path.islink(path):
                continue
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
    return total


def ensure_model(model: str, on_progress: ProgressFn | None = None) -> str:
    """Devuelve la ruta local del modelo, descargándolo (con progreso) si hace falta."""
    import huggingface_hub
    from huggingface_hub import constants

    repo = repo_id(model)
    try:
        return huggingface_hub.snapshot_download(repo, allow_patterns=ALLOW_PATTERNS, local_files_only=True)
    except Exception:  # noqa: BLE001 - no está en caché
        pass

    expected = 0
    try:
        info = huggingface_hub.HfApi().model_info(repo, files_metadata=True)
        from fnmatch import fnmatch

        expected = sum(
            s.size or 0 for s in info.siblings
            if any(fnmatch(s.rfilename, p) for p in ALLOW_PATTERNS)
        )
    except Exception:  # noqa: BLE001
        log.warning("No se pudo obtener el tamaño del modelo %s", repo)

    cache_repo = Path(constants.HF_HUB_CACHE) / f"models--{repo.replace('/', '--')}"
    done = threading.Event()

    def poll():
        while not done.wait(0.5):
            if on_progress:
                if expected:
                    on_progress(min(99, int(_folder_size(cache_repo) * 100 / expected)))
                else:
                    on_progress(-1)

    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    try:
        path = huggingface_hub.snapshot_download(repo, allow_patterns=ALLOW_PATTERNS)
    finally:
        done.set()
    if on_progress:
        on_progress(100)
    return path


class Transcriber:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.model = None
        self.device = "cpu"
        self.model_name = ""

    def load(self, on_status: StatusFn | None = None, on_progress: ProgressFn | None = None) -> None:
        """Carga el modelo. En modo auto intenta GPU y, si falla, usa CPU."""
        status = on_status or (lambda _m: None)
        wanted = self.cfg.device
        if wanted in ("auto", "cuda"):
            cuda_dlls.register(self.cfg.cuda_path)
            if cuda_dlls.cuda_device_count() > 0:
                try:
                    self._load("cuda", status, on_progress)
                    return
                except Exception as e:  # noqa: BLE001
                    log.warning("GPU no disponible (%s); usando CPU", e)
                    status("GPU no disponible, usando CPU")
            elif wanted == "cuda":
                status("No se encontró GPU NVIDIA, usando CPU")
        self._load("cpu", status, on_progress)

    def _load(self, device: str, status: StatusFn, on_progress: ProgressFn | None) -> None:
        from faster_whisper import WhisperModel

        name = self.cfg.model_for(device)
        status(f"Preparando modelo {name}…")
        path = ensure_model(name, on_progress)
        status(f"Cargando {name} en {'GPU' if device == 'cuda' else 'CPU'}…")
        model = WhisperModel(
            path,
            device=device,
            compute_type=COMPUTE_TYPE[device],
            cpu_threads=max(1, (os.cpu_count() or 4) - 1) if device == "cpu" else 0,
        )
        # Calentamiento: en GPU, aquí aparecen los errores de DLL/memoria.
        segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language="es", beam_size=1)
        list(segments)
        self.model, self.device, self.model_name = model, device, name
        log.info("Modelo %s cargado en %s", name, device)

    def _segments(self, audio: np.ndarray, prompt: str, fast: bool, words: bool):
        if self.model is None:
            raise RuntimeError("modelo no cargado")
        segments, _info = self.model.transcribe(
            audio,
            language=self.cfg.language or None,
            # En GPU sobra margen: beam search también en vivo. En CPU, las pasadas en vivo son voraces.
            beam_size=5 if self.device == "cuda" else (1 if fast else 2),
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            without_timestamps=not words,
            word_timestamps=words,
        )
        # Descarta segmentos que Whisper marca como probablemente sin voz.
        return [s for s in segments if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0)]

    def transcribe(self, audio: np.ndarray, prompt: str = "") -> str:
        return "".join(s.text for s in self._segments(audio, prompt, fast=False, words=False))

    def transcribe_words(self, audio: np.ndarray, prompt: str = "") -> list[Word]:
        """Pasada rápida (en vivo) con marcas de tiempo por palabra."""
        return [
            Word(w.word.strip(), w.start, w.end)
            for s in self._segments(audio, prompt, fast=True, words=True)
            for w in (s.words or [])
            if w.word.strip()
        ]
