"""Hace visibles las DLL de CUDA (cuBLAS/cuDNN) instaladas vía pip.

Busca en el extra `gwensper[cuda]` (paquetes nvidia-*) o en un PyTorch con
CUDA ya instalado. Si no hay ninguno, no hace nada y Gwensper funciona en CPU.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_PACKAGES = ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc", "nvidia.cuda_runtime")
_registered = False


def _candidate_dirs() -> list[Path]:
    dirs = []
    for pkg in _PACKAGES:
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ValueError):
            continue
        if spec and spec.submodule_search_locations:
            dirs += [Path(loc) / "bin" for loc in spec.submodule_search_locations]
    # Si ya existe un PyTorch con CUDA, trae cuBLAS/cuDNN compatibles (sin importar torch).
    try:
        spec = importlib.util.find_spec("torch")
        if spec and spec.origin:
            torch_lib = Path(spec.origin).parent / "lib"
            if (torch_lib / "cublas64_12.dll").exists():
                dirs.append(torch_lib)
    except (ImportError, ValueError):
        pass
    return [d for d in dirs if d.is_dir()]


def register(extra_dir: str = "") -> None:
    """`extra_dir`: carpeta con cuBLAS/cuDNN ya instalados (la detecta el instalador)."""
    global _registered
    if _registered or sys.platform != "win32":
        return
    _registered = True
    dirs = _candidate_dirs()
    if extra_dir and Path(extra_dir).is_dir():
        dirs.insert(0, Path(extra_dir))
    # Al revés: cada carpeta se antepone al PATH, así la primera queda con más prioridad.
    for bin_dir in reversed(dirs):
        os.add_dll_directory(str(bin_dir))
        # ctranslate2 carga cuBLAS con LoadLibrary, que busca en PATH.
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        log.info("DLLs CUDA: %s", bin_dir)


def cuda_device_count() -> int:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception:  # noqa: BLE001 - cualquier fallo equivale a "sin GPU"
        return 0
