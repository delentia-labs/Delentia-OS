"""
Round 73: which Whisper model hears a voice note. Measured on 30 real Thai clips (research/whisper_thai_eval_r73.json): CER tiny 0.593, base 0.364, small 0.214. voice.py therefore uses the best model
already in the cache, never downloads one, and always obeys DELENTIA_STT_MODEL.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from pathlib import Path

import pytest

from rct_control_plane import voice


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv(voice.STT_MODEL_ENV, raising=False)
    folder = tmp_path / "whisper"
    folder.mkdir()
    return folder


@pytest.mark.parametrize("present,expected", [(["tiny"], "tiny"), (["tiny", "base"], "base"), (["tiny", "base", "small"], "small"), (["base", "small"], "small"), ([], "tiny")])
def test_the_best_model_already_on_disk_is_used(cache, present, expected):
    for name in present:
        (cache / f"{name}.pt").write_bytes(b"x")
    assert voice.stt_model_name() == expected


def test_a_named_model_is_obeyed_even_when_a_better_one_is_present_and_nothing_is_downloaded(cache, monkeypatch):
    (cache / "small.pt").write_bytes(b"x")
    monkeypatch.setenv(voice.STT_MODEL_ENV, "tiny")
    assert voice.stt_model_name() == "tiny"
    assert [p.name for p in cache.iterdir()] == ["small.pt"]                  # choosing a model creates no file


def test_the_recorded_measurement_is_what_the_choice_rests_on():
    report = json.loads((Path(__file__).resolve().parents[2] / "research" / "whisper_thai_eval_r73.json").read_text(encoding="utf-8"))
    cer = {name: m["cer"] for name, m in report["models"].items()}
    assert report["clips"] == 30 and cer["tiny"] > cer["base"] > cer["small"] and cer["small"] <= 0.30 < cer["base"]
