"""Protect Thai capture against arbitrary OS byte boundaries and glyph clipping."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('demo_recording', Path(__file__).resolve().parents[1] / 'scripts/demo_recording.py')
recording = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recording)


def test_utf8_at_every_possible_split_is_lossless():
    text = 'ราคา 12,500 บาท สยามแอร์ ไทยคูลลิ่ง บางกอกเทคนิค น้ำ กำลัง ขั้นที่ ๗\r\n'
    raw = text.encode('utf-8')
    for offset in range(len(raw) + 1):
        assert recording.decode_chunks([raw[:offset], raw[offset:]]) == text
    assert recording.decode_chunks([bytes([b]) for b in raw]) == text
    with pytest.raises(UnicodeDecodeError):
        recording.decode_chunks([b'\xe0'])


def test_terminal_runs_preserve_thai_combining_marks_as_text():
    pyte = pytest.importorskip('pyte')
    text = 'ราคา: น้ำ กำลัง ชั้นที่ ๗ | 12,500 บาท'
    screen = recording.unicode_screen(100, 4)
    pyte.Stream(screen).feed(text)
    runs = recording.text_runs(screen.buffer[0], 100)
    assert ''.join(r[1] for r in runs).rstrip() == text
    assert any('กำลัง' in value for _, value, thai in runs if thai)
    # Combining marks must belong to the same drawn run as their base letters.
    assert any('ชั้นที่' in value for _, value, thai in runs if thai)
