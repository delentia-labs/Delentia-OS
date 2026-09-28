"""
Round 48: rct_control_plane/delta_v2.py must produce byte-identical output
to the TypeScript original (delentia-mcp-ecosystem packages/delta
compressContext). fixtures/delta_v2/golden_ts_outputs.json holds the SHA-256
of the TypeScript output for 360 real cases: the Round 46 benchmark corpora
(a real build/test log, real TypeScript source, a real README) plus a Thai
snippet, x 30 intents (the benchmark's questions + extras, one empty) x 3
modes (aggressive+outline, aggressive, plain).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import hashlib
import json
from pathlib import Path

import pytest

from rct_control_plane.delta_v2 import compress_context, focus_keywords

FIX = Path(__file__).resolve().parent / "fixtures" / "delta_v2"
GOLDEN = json.loads((FIX / "golden_ts_outputs.json").read_text(encoding="utf-8"))["cases"]
CORPORA = {name: (FIX / name).read_bytes().decode("utf-8") for name in {c["corpus"] for c in GOLDEN}}  # exact bytes, like Node readFileSync


def test_golden_set_is_the_full_matrix():
    assert len(GOLDEN) == 360 and len(CORPORA) == 4


@pytest.mark.parametrize("case", GOLDEN, ids=lambda c: f"{c['corpus']}|{(c['intent_focus'] or '-')[:30]}|"
                         f"{'agg' if c['aggressive_mode'] else 'plain'}{'+outline' if c['outline'] else ''}")
def test_python_port_matches_typescript_byte_for_byte(case):
    r = compress_context(CORPORA[case["corpus"]], intent_focus=case["intent_focus"],
                         aggressive_mode=case["aggressive_mode"], outline=case["outline"])
    assert hashlib.sha256(r.compressed_delta_text.encode("utf-8")).hexdigest() == case["sha256"]
    assert r.compressed_char_count == case["compressed_char_count"]
    assert r.estimated_original_tokens == case["estimated_original_tokens"]
    assert r.estimated_compressed_tokens == case["estimated_compressed_tokens"]
    assert r.reduction_percentage == case["reduction_percentage"]


def test_focus_keywords_behaviour():
    assert focus_keywords("What is the running version of @delentia/mcp-delta?") == ["runn", "version", "@delentia/mcp-delta"]
    assert focus_keywords("the and of") == []


def test_aggressive_mode_really_compresses_a_real_log():
    raw = CORPORA["build_and_test_run.log"]
    r = compress_context(raw, intent_focus="Which tests failed and why?", aggressive_mode=True, outline=True)
    assert r.reduction_percentage > 50
    assert "error" in r.compressed_delta_text.lower() or "fail" in r.compressed_delta_text.lower()
