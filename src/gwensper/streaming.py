"""Dictado en vivo con "acuerdo local" (local agreement) y marcas de tiempo por palabra.

Mientras hablas, se transcribe cada ~1 s el audio de la frase en curso que todavía no
se ha escrito. Las palabras en las que coinciden dos pasadas seguidas se confirman y
se escriben; se recuerda en qué segundo terminó la última, y la siguiente pasada
empieza ahí, con lo confirmado como contexto. Así nunca se vuelve a comparar lo ya
escrito (no hay duplicados) y la transcripción final solo completa el audio restante.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_STRIP = re.compile(r"[^\w]+", re.UNICODE)


def _norm(word: str) -> str:
    return _STRIP.sub("", word.lower())


@dataclass
class Word:
    text: str
    start: float  # segundos desde el inicio de la frase
    end: float


class LiveTranscript:
    def __init__(self, prompt: str = "", context_chars: int = 200) -> None:
        self.base_prompt = prompt  # lo escrito antes de esta frase
        self.context_chars = context_chars
        self.committed: list[str] = []
        self.offset = 0.0  # segundo del audio donde termina lo ya escrito
        self._previous: list[Word] = []

    @property
    def prompt(self) -> str:
        text = " ".join(filter(None, [self.base_prompt.strip(), *self.committed]))
        return text[-self.context_chars:]

    def update(self, words: list[Word]) -> list[str]:
        """Pasada parcial sobre el audio desde `offset`; devuelve las palabras recién confirmadas."""
        agree = 0
        for a, b in zip(self._previous, words):
            if _norm(a.text) != _norm(b.text):
                break
            agree += 1
        # La última palabra puede estar cortada a la mitad: nunca se confirma en parcial.
        agree = min(agree, len(words) - 1)
        if agree <= 0:
            self._previous = words
            return []
        new = words[:agree]
        self.committed.extend(w.text for w in new)
        self.offset = new[-1].end
        self._previous = words[agree:]
        return [w.text for w in new]

    def reset_hypothesis(self) -> None:
        self._previous = []
