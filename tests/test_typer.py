from gwensper.typer import tokenize


def test_tokens_keep_following_space():
    assert tokenize("Hola, ¿qué tal?") == ["Hola, ", "¿qué ", "tal?"]


def test_joining_tokens_rebuilds_text_exactly():
    for text in (" Año nuevo, vida nueva.", "uno  dos\ntres ", "ñandú… sí", "", "   "):
        assert "".join(tokenize(text)) == text


def test_leading_space_is_its_own_token():
    assert tokenize(" Hola mundo") == [" ", "Hola ", "mundo"]
