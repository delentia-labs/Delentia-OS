"""
Round 38: real test proving process_intent_deep_pipeline()'s new
Phase 6 intent-delta-compression wiring - the redesigned, intent-
centric ALGO-25 mechanism tracking real consecutive-call deltas.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_first_call_in_a_process_has_no_prior_state_to_diff_against():
    kernel = AlgorithmKernel41()
    assert kernel._last_intent_state is None
    result = asyncio.run(kernel.process_intent_deep_pipeline("Deploy the payment service."))
    assert result["phase_6_intent_delta_compression"] is None
    assert kernel._last_intent_state is not None
    assert kernel._last_intent_state["intent"] == "Deploy the payment service."


def test_second_call_produces_a_real_measured_intent_delta():
    kernel = AlgorithmKernel41()
    asyncio.run(kernel.process_intent_deep_pipeline("Deploy the payment service."))
    result = asyncio.run(kernel.process_intent_deep_pipeline("Deploy the payment retry service."))

    compression = result["phase_6_intent_delta_compression"]
    assert compression is not None
    assert compression["op_count"] >= 1
    assert compression["full_new_state_bytes"] > 0
    assert compression["old_state_tokens_approx"] is not None
    assert compression["new_state_tokens_approx"] is not None


def test_expanded_tracked_state_includes_the_real_rct7_decomposition_and_mee_summary():
    """Round 40: the tracked intent state was expanded (per Round 39's
    own finding that the original 4-field state never crossed zstd's
    real 200-byte activation threshold) to include the real, full RCT-7
    decomposition and MEE growth summary - proves both are genuinely
    present now, not just declared in a docstring."""
    kernel = AlgorithmKernel41()
    asyncio.run(kernel.process_intent_deep_pipeline("Deploy the payment service."))
    state = kernel._last_intent_state
    assert "rct7_decomposition" in state
    assert len(state["rct7_decomposition"]) == 7  # real RCT-7 always produces 7 steps
    assert "mee_growth_summary" in state
    assert isinstance(state["mee_growth_summary"], dict)


def test_zstd_genuinely_activates_now_with_the_expanded_state():
    """Round 40: the exact real gap Round 39 found (zstd_applied: False
    in every tested case against the original small 4-field state) -
    with the real, full RCT-7 decomposition text now included, the
    serialized structural patch genuinely crosses the real byte
    threshold and zstd actually participates."""
    kernel = AlgorithmKernel41()
    asyncio.run(kernel.process_intent_deep_pipeline(
        "Deploy the new payment retry logic to production after verifying idempotency."
    ))
    result = asyncio.run(kernel.process_intent_deep_pipeline(
        "Deploy the new payment retry logic to production after verifying idempotency and rollback support."
    ))
    compression = result["phase_6_intent_delta_compression"]
    assert compression["structural_patch_bytes"] >= 200
    assert compression["zstd_applied"] is True
