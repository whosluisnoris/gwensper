"""Accesos directos de Windows: menú Inicio e inicio automático."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

from . import APP_NAME
from .config import data_dir

log = logging.getLogger(__name__)


def _programs_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def start_menu_link() -> Path:
    return _programs_dir() / f"{APP_NAME}.lnk"


def startup_link() -> Path:
    return _programs_dir() / "Startup" / f"{APP_NAME}.lnk"


def launch_target() -> tuple[str, str]:
    """(ejecutable, argumentos) para abrir Gwensper sin consola."""
    candidates = [shutil.which("gwensper")]
    for scheme in (f"{os.name}_user", None):
        try:
            scripts = sysconfig.get_path("scripts", scheme) if scheme else sysconfig.get_path("scripts")
            candidates.append(str(Path(scripts) / "gwensper.exe"))
        except KeyError:
            pass
    for c in candidates:
        if c and Path(c).exists():
            return c, ""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else Path(sys.executable)), "-m gwensper"


def _icon_file() -> Path:
    from .icon import asset_path, save_ico

    return asset_path("icon.ico") or save_ico(data_dir() / "gwensper.ico")


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def create_shortcut(link: Path, args_extra: str = "") -> Path:
    target, args = launch_target()
    args = f"{args} {args_extra}".strip()
    link.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(str(link)) + ");"
        f"$s.TargetPath={_ps_quote(target)};"
        f"$s.Arguments={_ps_quote(args)};"
        f"$s.WorkingDirectory={_ps_quote(str(Path.home()))};"
        f"$s.IconLocation={_ps_quote(str(_icon_file()))};"
        "$s.Description='Dictado por voz con Whisper';"
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.info("Acceso directo creado: %s -> %s %s", link, target, args)
    return link


def install_start_menu() -> Path:
    return create_shortcut(start_menu_link())


def uninstall_start_menu() -> None:
    for link in (start_menu_link(), startup_link()):
        link.unlink(missing_ok=True)


def autostart_enabled() -> bool:
    return startup_link().exists()


def set_autostart(enabled: bool) -> None:
    if enabled:
        # Al iniciar Windows arranca en la bandeja, sin abrir la ventana.
        create_shortcut(startup_link(), "--background")
    else:
        startup_link().unlink(missing_ok=True)
