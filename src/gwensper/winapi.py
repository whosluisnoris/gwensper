"""Llamadas Win32 vía ctypes: escribir texto, atajos globales y estilos de ventana."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_V = 0x56

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

ULONG_PTR = wintypes.WPARAM


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags))


def _send(events: list[INPUT]) -> None:
    if not events:
        return
    arr = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
    if sent != len(events):
        raise ctypes.WinError(ctypes.get_last_error())


def type_unicode(text: str) -> None:
    """Escribe texto en la ventana con foco, independiente del layout del teclado."""
    events: list[INPUT] = []
    for ch in text:
        if ch == "\n":
            events += [_key(vk=VK_RETURN), _key(vk=VK_RETURN, flags=KEYEVENTF_KEYUP)]
            continue
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):  # pares sustitutos para emojis, etc.
            unit = int.from_bytes(data[i:i + 2], "little")
            events += [
                _key(scan=unit, flags=KEYEVENTF_UNICODE),
                _key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
            ]
    _send(events)


def send_ctrl_v() -> None:
    _send([
        _key(vk=VK_CONTROL), _key(vk=VK_V),
        _key(vk=VK_V, flags=KEYEVENTF_KEYUP), _key(vk=VK_CONTROL, flags=KEYEVENTF_KEYUP),
    ])


# ---------- atajos globales ----------
_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
         "win": MOD_WIN, "super": MOD_WIN}
_NAMED_VK = {
    "space": 0x20, "espacio": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "pause": 0x13, "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "scrolllock": 0x91, "capslock": 0x14,
}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'ctrl+alt+d' -> (modificadores, código virtual). Lanza ValueError si no es válido."""
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("atajo vacío")
    mods, key = 0, parts[-1]
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"modificador desconocido: {p}")
        mods |= _MODS[p]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in _NAMED_VK:
        vk = _NAMED_VK[key]
    else:
        raise ValueError(f"tecla desconocida: {key}")
    return mods, vk


def register_hotkey(hwnd: int, hotkey_id: int, spec: str) -> bool:
    mods, vk = parse_hotkey(spec)
    return bool(user32.RegisterHotKey(wintypes.HWND(hwnd), hotkey_id, mods | MOD_NOREPEAT, vk))


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    user32.UnregisterHotKey(wintypes.HWND(hwnd), hotkey_id)


# ---------- ventana flotante ----------
def make_no_activate(hwnd: int) -> None:
    """La ventana no roba el foco al hacer clic ni aparece en la barra de tareas."""
    get = user32.GetWindowLongPtrW
    get.restype = ctypes.c_ssize_t
    get.argtypes = [wintypes.HWND, ctypes.c_int]
    set_ = user32.SetWindowLongPtrW
    set_.restype = ctypes.c_ssize_t
    set_.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    style = get(hwnd, GWL_EXSTYLE)
    set_(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)


def set_app_user_model_id(app_id: str) -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass
