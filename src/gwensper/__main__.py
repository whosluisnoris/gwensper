"""Punto de entrada: `gwensper` (o `python -m gwensper`)."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import APP_NAME, __version__
from .config import data_dir

# Sin barras de progreso de Hugging Face: con pythonw no hay consola donde escribirlas.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
# Sin avisos de Hugging Face (p. ej. "unauthenticated requests"): no aplican a una app de escritorio.
os.environ.setdefault("HF_HUB_VERBOSITY", "error")


def _setup_logging(verbose: bool) -> None:
    log_dir = data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_dir / "gwensper.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    for noisy in ("httpx", "httpcore", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


def _ensure_std_streams() -> None:
    # pythonw deja stdout/stderr en None; algunas librerías escriben ahí y fallarían.
    if sys.stdout is None or sys.stderr is None:
        devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull


def _message(text: str, error: bool = False) -> None:
    """Muestra el resultado de un comando aunque no haya consola."""
    if sys.stdout is not None and sys.stdout.isatty():
        print(text)
        return
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10 if error else 0x40)


def _download_model(name: str) -> int:
    """Descarga con progreso en consola (lo usa el instalador)."""
    from .models import BY_NAME
    from .transcriber import ensure_model

    info = BY_NAME.get(name)
    from .models import is_downloaded

    if is_downloaded(name):
        print(f"Ya tienes el modelo {name}: no hace falta descargarlo.", flush=True)
        return 0
    print(f"Descargando el modelo {name}" + (f" (unos {info.size_mb} MB)" if info else "") + "...", flush=True)
    last = [-10]

    def progress(pct: int) -> None:
        if pct >= last[0] + 10 or pct == 100:
            last[0] = pct
            print(f"  {pct} %", flush=True)

    try:
        ensure_model(name, progress)
    except Exception as e:  # noqa: BLE001
        print(f"No se pudo descargar el modelo: {e}", file=sys.stderr)
        return 1
    print("Modelo listo.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gwensper", description="Dictado por voz con Whisper.")
    parser.add_argument("--install-shortcut", action="store_true", help="crear acceso directo en el menú Inicio")
    parser.add_argument("--uninstall-shortcut", action="store_true", help="quitar accesos directos")
    parser.add_argument("--test-audio", metavar="ARCHIVO", help="usar un archivo de audio en lugar del micrófono")
    parser.add_argument("--download-model", metavar="MODELO",
                        help="descargar un modelo (tiny, base, small, medium, large-v3-turbo, large-v3) y salir")
    parser.add_argument("--background", action="store_true", help="iniciar en la bandeja, sin la ventana")
    parser.add_argument("--verbose", action="store_true", help="registro detallado")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    from . import shortcuts

    if args.install_shortcut:
        try:
            link = shortcuts.install_start_menu()
        except Exception as e:  # noqa: BLE001
            _message(f"No se pudo crear el acceso directo: {e}", error=True)
            return 1
        _message(f"Listo: {APP_NAME} ya aparece en el menú Inicio.\n{link}")
        return 0
    if args.download_model:
        return _download_model(args.download_model)
    if args.uninstall_shortcut:
        shortcuts.uninstall_start_menu()
        _message("Accesos directos eliminados.")
        return 0

    _ensure_std_streams()
    from .app import run

    return run(test_audio=args.test_audio, background=args.background)


if __name__ == "__main__":
    sys.exit(main())
