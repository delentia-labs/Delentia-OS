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
