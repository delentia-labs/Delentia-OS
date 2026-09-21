"""
Round 38: real tests for DeltaEngine's redesigned compression - added
after Round 38's own empirical measurement found the ORIGINAL
compute_delta() actually EXPANDS data on average (-24.6% across 5
varied cases) and crashes on any nested dict/list value.
compute_structural_delta()/compress_intent_delta() are the real fix:
a genuine recursive key-aware diff, combined with algo_03's own real
zstd mechanism, applied only past a real size threshold.

The original compute_delta()/DeltaDiff are untouched (Zero-Delete) -
see test_delta_memory_incremental_real.py and other pre-existing tests
for that mechanism's own coverage, unaffected by this file.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algo_25_delta_block import DeltaEngine


class TestStructuralDeltaHandlesWhatTheOriginalCouldNot:
    def test_nested_dict_state_does_not_crash(self):
        """The exact real crash Round 38 found: compute_delta() raises
        TypeError: unhashable type: 'dict' on nested state."""
        engine = DeltaEngine()
        old = {"intent": "deploy", "metadata": {"user": "architect", "tags": ["prod"]}, "score": 0.9}
        new = {"intent": "deploy", "metadata": {"user": "architect", "tags": ["prod", "urgent"]}, "score": 0.95}
        result = engine.compute_structural_delta(old, new)
        assert result["op_count"] >= 1
        paths = {op["path"] for op in result["ops"]}
        assert any("/metadata/tags" in p for p in paths)
        assert any(op["path"] == "/score" for op in result["ops"])

    def test_nested_list_state_does_not_crash(self):
        engine = DeltaEngine()
        old = {"steps": [{"name": "a", "done": False}, {"name": "b", "done": False}]}
        new = {"steps": [{"name": "a", "done": True}, {"name": "b", "done": False}]}
        result = engine.compute_structural_delta(old, new)
        assert any(op["path"] == "/steps/0/done" for op in result["ops"])

    def test_value_swap_between_keys_is_now_correctly_detected(self):
        """The exact real blind spot Round 38 found: compute_delta()
        reports is_empty()=True for a real semantic change (two keys'
        values swapped)."""
        engine = DeltaEngine()
        old = {"field_a": "hello", "field_b": "world"}
        new = {"field_a": "world", "field_b": "hello"}
        result = engine.compute_structural_delta(old, new)
        assert result["op_count"] == 2
        assert {op["path"] for op in result["ops"]} == {"/field_a", "/field_b"}

    def test_identical_states_produce_zero_ops(self):
        engine = DeltaEngine()
        state = {"a": 1, "b": {"c": 2}}
        result = engine.compute_structural_delta(state, dict(state))
        assert result["op_count"] == 0
        assert result["ops"] == []

    def test_added_and_removed_keys_are_both_detected(self):
        engine = DeltaEngine()
        old = {"a": 1, "b": 2}
        new = {"a": 1, "c": 3}
        result = engine.compute_structural_delta(old, new)
        ops_by_path = {op["path"]: op for op in result["ops"]}
        assert ops_by_path["/b"]["op"] == "remove"
        assert ops_by_path["/c"]["op"] == "add"


class TestCompressIntentDeltaRealThresholdBehavior:
    def test_a_tiny_delta_below_threshold_skips_zstd(self):
        """Round 38's own measurement: zstd expands payloads under
        ~100-150 bytes due to frame overhead - the real threshold must
        actually skip compression for genuinely small patches."""
        engine = DeltaEngine()
        old = {"status": "pending"}
        new = {"status": "done"}
        result = engine.compress_intent_delta(old, new, zstd_min_bytes=200)
        assert result["zstd_applied"] is False
        assert result["final_bytes"] == result["structural_patch_bytes"]

    def test_a_large_repetitive_delta_above_threshold_uses_zstd_and_shrinks(self):
        engine = DeltaEngine()
        old = {"intent": "x" * 50}
        new = {"intent": "y" * 2000}
        result = engine.compress_intent_delta(old, new, zstd_min_bytes=50)
        assert result["zstd_applied"] is True
        assert result["final_bytes"] < result["structural_patch_bytes"]

    def test_real_token_counts_are_reported_and_sane(self):
        """Note: for a SINGLE top-level field whose value is entirely
        rewritten, the patch is honestly NOT smaller in tokens than the
        new state - a "replace" op still carries the full new value plus
        JSON-wrapper overhead ("op"/"path" keys). This is a real, expected
        limitation of value-level diffing, not a bug: there's no shared
        structure to exploit when 100% of a single field changed. Real
        token reduction requires an unchanged surrounding structure - see
        test_a_real_large_context_case_achieves_genuine_positive_compression."""
        engine = DeltaEngine()
        old = {"intent": "deploy the payment service"}
        new = {"intent": "deploy the payment retry service with idempotency"}
        result = engine.compress_intent_delta(old, new)
        assert result["old_state_tokens_approx"] is not None
        assert result["new_state_tokens_approx"] is not None
        assert result["patch_tokens_approx"] is not None
        assert result["new_state_tokens_approx"] > result["old_state_tokens_approx"]

    def test_a_real_large_context_case_achieves_genuine_positive_compression(self):
        """Proof the redesign actually closes the gap Round 38 found -
        unlike the original compute_delta()'s -24.6% average, a real
        large-context-small-change case now genuinely shrinks."""
        engine = DeltaEngine()
        old = {f"field_{i}": f"value_{i}_" + ("x" * 50) for i in range(30)} | {"status": "pending"}
        new = {f"field_{i}": f"value_{i}_" + ("x" * 50) for i in range(30)} | {"status": "done"}
        result = engine.compress_intent_delta(old, new)
        assert result["byte_reduction_pct"] > 90.0
        assert result["patch_tokens_approx"] < result["new_state_tokens_approx"]
        assert result["token_reduction_pct_approx"] > 80.0

    def test_the_original_compute_delta_is_completely_unaffected_zero_delete(self):
        """Zero-Delete proof: the pre-existing method's exact behavior
        (including its real limitations) is untouched."""
        engine = DeltaEngine()
        old = {"a": "x", "b": "y"}
        new = {"a": "x", "b": "z"}
        diff = engine.compute_delta(old, new)
        assert diff.added == ["z"]
        assert diff.removed == ["y"]
