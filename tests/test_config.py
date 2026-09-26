import json

import pytest

from gwensper.config import Config
from gwensper.winapi import parse_hotkey


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(hotkey="ctrl+shift+space", language="en", overlay_x=10, overlay_y=20)
    cfg.save(path)
    assert Config.load(path) == cfg


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert Config.load(tmp_path / "nope.json") == Config()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert Config.load(bad) == Config()


def test_invalid_values_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"silence_ms": "mucho", "device": "tpu", "unknown": 1, "max_phrase_s": 15}),
                    encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.silence_ms == Config().silence_ms
    assert cfg.device == "auto"
    assert cfg.max_phrase_s == 15


def test_model_for_device():
    assert Config().model_for("cpu") == "small"
    assert Config().model_for("cuda") == "large-v3-turbo"
    assert Config(model="base").model_for("cuda") == "base"


def test_parse_hotkey():
    assert parse_hotkey("ctrl+alt+d") == (0x2 | 0x1, ord("D"))
    assert parse_hotkey("F9") == (0, 0x78)
    assert parse_hotkey("ctrl + shift + space") == (0x2 | 0x4, 0x20)
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+hyper+x")
    with pytest.raises(ValueError):
        parse_hotkey("")
