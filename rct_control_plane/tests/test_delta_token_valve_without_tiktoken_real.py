"""
Round 50: the token safety valve keeps working when tiktoken cannot be
imported (not installed, or its DLL blocked by Windows Application Control,
as on the Architect's machine). Before, the token counts became None, the
valve switched itself off, and an unrelated turn was sent as a patch larger
than the full state.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algo_25_delta_block import DeltaEngine


def _without_tiktoken(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # makes `import tiktoken` raise ImportError


def test_unrelated_turn_falls_back_to_the_full_state_without_tiktoken(monkeypatch):
    _without_tiktoken(monkeypatch)
    old = {"topic": "payment", "details": {f"k{i}": "v" * 40 for i in range(20)}}
    new = {"trivia_answer": "4"}
    result = DeltaEngine().compress_intent_delta(old, new)
    assert result["token_count_method"] == "chars_div_4_estimate"
    assert result["used_token_fallback_to_full_state"] is True
    assert result["patch_tokens_approx"] == result["new_state_tokens_approx"]


def test_a_small_change_in_a_large_state_still_compresses_without_tiktoken(monkeypatch):
    _without_tiktoken(monkeypatch)
    old = {f"field_{i}": f"value_{i}_" + ("x" * 50) for i in range(30)} | {"status": "pending"}
    new = dict(old, status="done")
    result = DeltaEngine().compress_intent_delta(old, new)
    assert result["token_count_method"] == "chars_div_4_estimate"
    assert result["used_token_fallback_to_full_state"] is False
    assert result["patch_tokens_approx"] < result["new_state_tokens_approx"]


def test_the_real_tokenizer_is_reported_when_it_loads():
    try:
        import tiktoken  # noqa: F401
    except ImportError:
        import pytest
        pytest.skip("tiktoken cannot be imported here")
    result = DeltaEngine().compress_intent_delta({"a": 1}, {"a": 2})
    assert result["token_count_method"] == "tiktoken_cl100k"
