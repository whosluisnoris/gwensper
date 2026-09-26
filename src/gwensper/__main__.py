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
    for noisy in ("httpx", "httpcore", "huggingface_hub", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gwensper", description="Dictado por voz con Whisper.")
    parser.add_argument("--install-shortcut", action="store_true", help="crear acceso directo en el menú Inicio")
    parser.add_argument("--uninstall-shortcut", action="store_true", help="quitar accesos directos")
    parser.add_argument("--test-audio", metavar="ARCHIVO", help="usar un archivo de audio en lugar del micrófono")
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
    if args.uninstall_shortcut:
        shortcuts.uninstall_start_menu()
        _message("Accesos directos eliminados.")
        return 0

    _ensure_std_streams()
    from .app import run

    return run(test_audio=args.test_audio)


if __name__ == "__main__":
    sys.exit(main())
