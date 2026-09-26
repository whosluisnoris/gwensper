from gwensper.streaming import LiveTranscript, Word


def words(text: str, start: float = 0.0, step: float = 0.4) -> list[Word]:
    return [Word(w, start + i * step, start + (i + 1) * step) for i, w in enumerate(text.split())]


def test_first_pass_commits_nothing():
    lt = LiveTranscript()
    assert lt.update(words("Hola esta es")) == []
    assert lt.offset == 0.0


def test_agreed_words_are_committed_except_the_last():
    lt = LiveTranscript()
    lt.update(words("Hola, esta es una"))
    assert lt.update(words("Hola, esta es una prueba")) == ["Hola,", "esta", "es", "una"]
    assert lt.offset == 1.6  # fin de "una"


def test_comparison_ignores_case_and_punctuation():
    lt = LiveTranscript()
    lt.update(words("hola esta es"))
    assert lt.update(words("Hola, esta es una")) == ["Hola,", "esta", "es"]


def test_next_pass_only_covers_audio_after_offset():
    lt = LiveTranscript()
    lt.update(words("Me estoy dando"))
    assert lt.update(words("Me estoy dando cuenta")) == ["Me", "estoy", "dando"]
    # La siguiente pasada transcribe desde offset: sus palabras son solo las nuevas.
    assert lt.update(words("cuenta de que", start=lt.offset)) == ["cuenta"]
    # "de que" coincide con lo pendiente de la pasada anterior; "el" aún no.
    assert lt.update(words("de que el texto", start=lt.offset)) == ["de", "que"]
    assert lt.committed == ["Me", "estoy", "dando", "cuenta", "de", "que"]


def test_changed_earlier_words_never_duplicate():
    lt = LiveTranscript()
    lt.update(words("si a oras palabras"))
    assert lt.update(words("si ahora las palabras van")) == ["si"]
    # Lo ya escrito no se vuelve a comparar: la siguiente pasada empieza tras "si".
    assert lt.update(words("ahora las palabras", start=lt.offset)) == ["ahora", "las"]
    assert lt.committed == ["si", "ahora", "las"]


def test_prompt_includes_previous_text_and_committed_words():
    lt = LiveTranscript(prompt="Texto anterior.")
    lt.update(words("Hola mundo de"))
    lt.update(words("Hola mundo de nuevo"))
    assert lt.prompt == "Texto anterior. Hola mundo de"
