"""Catálogo de modelos de Whisper y su gestión en disco (caché de Hugging Face)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .transcriber import ALLOW_PATTERNS, ProgressFn, ensure_model, repo_id

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelInfo:
    name: str
    title: str
    description: str
    size_mb: int
    precision: int  # 1..5
    cpu_speed: str
    gpu_speed: str


CATALOG = [
    ModelInfo("tiny", "Tiny", "El más ligero. Para probar o para PCs muy modestas.", 75, 1,
              "Muy rápido", "Instantáneo"),
    ModelInfo("base", "Base", "Rápido y ligero, con errores en palabras poco comunes.", 145, 2,
              "Rápido", "Instantáneo"),
    ModelInfo("small", "Small", "El equilibrio para dictar en CPU.", 484, 3,
              "Aceptable", "Muy rápido"),
    ModelInfo("medium", "Medium", "Más preciso que small, pero lento sin GPU.", 1530, 4,
              "Lento", "Rápido"),
    ModelInfo("large-v3-turbo", "Large v3 Turbo", "Casi tan preciso como large-v3 y mucho más rápido. "
              "El recomendado con GPU.", 1620, 4, "Muy lento", "Rápido"),
    ModelInfo("large-v3", "Large v3", "La máxima precisión. Pesado: necesita una GPU con memoria.", 3090, 5,
              "Muy lento", "Aceptable"),
]
BY_NAME = {m.name: m for m in CATALOG}


def _cached_repo(name: str):
    """Entrada de la caché de Hugging Face para el modelo, o None."""
    from huggingface_hub import scan_cache_dir

    wanted = repo_id(name)
    try:
        return next((r for r in scan_cache_dir().repos if r.repo_id == wanted), None)
    except Exception:  # noqa: BLE001 - caché inexistente o ilegible
        return None


def is_downloaded(name: str) -> bool:
    import huggingface_hub

    try:
        huggingface_hub.snapshot_download(repo_id(name), allow_patterns=ALLOW_PATTERNS, local_files_only=True)
        return True
    except Exception:  # noqa: BLE001 - no está (o está incompleto) en la caché
        return False


def disk_size_mb(name: str) -> int:
    # La caché guarda los archivos en un almacén compartido con enlaces; scan_cache_dir
    # calcula el tamaño real sin contarlos dos veces.
    repo = _cached_repo(name)
    return repo.size_on_disk // (1024 * 1024) if repo else 0


def download(name: str, on_progress: ProgressFn | None = None) -> str:
    return ensure_model(name, on_progress)


def delete(name: str) -> None:
    from huggingface_hub import scan_cache_dir

    repo = _cached_repo(name)
    if repo is None:
        return
    hashes = [rev.commit_hash for rev in repo.revisions]
    strategy = scan_cache_dir().delete_revisions(*hashes)
    log.info("Eliminando modelo %s (%s)", name, strategy.expected_freed_size_str)
    strategy.execute()
