from gwensper.postprocess import clean, is_hallucination, join


def test_clean_normalizes_whitespace():
    assert clean("  Hola,   mundo.\n") == "Hola, mundo."


def test_known_hallucinations_are_dropped():
    assert clean("Subtítulos realizados por la comunidad de Amara.org") == ""
    assert clean("¡Gracias por ver el video!") == ""
    assert is_hallucination(" you")


def test_real_speech_is_kept():
    assert clean("Gracias por la reunión de hoy.") == "Gracias por la reunión de hoy."
    assert clean("Gracias.") == "Gracias."


def test_join_adds_space_between_phrases():
    assert join("", "Hola.") == "Hola."
    assert join("Hola.", "¿Qué tal?") == " ¿Qué tal?"
    assert join("Hola ", "mundo") == "mundo"
    assert join("Hola", ", mundo") == ", mundo"
