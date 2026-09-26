import numpy as np

from gwensper.segmenter import FRAME_LEN, SAMPLE_RATE, Segmenter


def _frames(signal: np.ndarray):
    for i in range(len(signal) // FRAME_LEN):
        yield signal[i * FRAME_LEN:(i + 1) * FRAME_LEN]


def _noise(seconds: float, amp: float = 0.002, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(seconds * SAMPLE_RATE)) * amp).astype(np.float32)


def _voice(seconds: float, amp: float = 0.2) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * t) * amp).astype(np.float32)


def _run(seg: Segmenter, signal: np.ndarray) -> list[np.ndarray]:
    out = []
    for f in _frames(signal):
        out += seg.feed(f)
    return out


def test_silence_produces_nothing():
    assert _run(Segmenter(), _noise(3)) == []


def test_two_phrases_split_by_pause():
    sig = np.concatenate([_noise(1), _voice(1.0), _noise(1), _voice(1.5), _noise(1)])
    phrases = _run(Segmenter(silence_ms=600), sig)
    assert len(phrases) == 2
    # Cada frase contiene la voz completa (más pre-roll y un poco de cola).
    assert 1.0 <= len(phrases[0]) / SAMPLE_RATE <= 1.7
    assert 1.5 <= len(phrases[1]) / SAMPLE_RATE <= 2.2


def test_short_pause_does_not_split():
    sig = np.concatenate([_noise(1), _voice(0.8), _noise(0.2), _voice(0.8), _noise(1)])
    assert len(_run(Segmenter(silence_ms=600), sig)) == 1


def test_click_is_ignored():
    sig = np.concatenate([_noise(1), _voice(0.09), _noise(1.5)])
    assert _run(Segmenter(), sig) == []


def test_long_speech_is_cut_at_max_length():
    sig = np.concatenate([_noise(0.5), _voice(5.0), _noise(1)])
    phrases = _run(Segmenter(max_phrase_s=2.0), sig)
    assert len(phrases) >= 2
    assert all(len(p) / SAMPLE_RATE <= 2.05 for p in phrases)


def test_flush_returns_phrase_in_progress():
    seg = Segmenter()
    _run(seg, np.concatenate([_noise(1), _voice(1.0)]))
    tail = seg.flush()
    assert tail is not None and len(tail) / SAMPLE_RATE >= 1.0
    assert seg.flush() is None
