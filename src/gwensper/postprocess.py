"""Limpieza del texto transcrito antes de escribirlo."""
from __future__ import annotations

import re
import unicodedata

# Frases que Whisper "alucina" con silencio o ruido (vienen de subtítulos de YouTube).
_HALLUCINATION_SUBSTRINGS = (
    "amara.org",
    "subtítulos realizados por",
    "subtitulos realizados por",
    "subtítulos por la comunidad",
    "subtitulado por",
)
_HALLUCINATION_EXACT = {
    "gracias por ver el video",
    "gracias por ver",
    "gracias por ver el vídeo",
    "suscríbete",
    "suscribete",
    "thanks for watching",
    "thank you for watching",
    "you",
    "",
}

_NO_SPACE_BEFORE = set(".,;:!?)]}»”%")


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFC", text).lower().strip()
    return re.sub(r"[\s¡!¿?.,;:\"'…-]+", " ", t).strip()


def is_hallucination(text: str) -> bool:
    norm = _normalize(text)
    if norm in _HALLUCINATION_EXACT:
        return True
    low = text.lower()
    return any(s in low for s in _HALLUCINATION_SUBSTRINGS)


def clean(text: str) -> str:
    """Normaliza espacios; devuelve "" si el texto debe descartarse."""
    text = re.sub(r"\s+", " ", text).strip()
    if is_hallucination(text):
        return ""
    return text


def join(previous: str, text: str) -> str:
    """Antepone un espacio si hace falta para unir con lo ya escrito."""
    if not text or not previous:
        return text
    if previous[-1].isspace() or text[0] in _NO_SPACE_BEFORE:
        return text
    return " " + text
