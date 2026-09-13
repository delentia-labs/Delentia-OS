"""
Regression tests for wiring intent_compiler.py's real decomposition into
ALGO-01's D/I inputs.

Context: an audit on 2026-09-13 found process_intent_full_pipeline() called
`self.algo_01_fdia(0.98, 0.96, 1.0)` with hardcoded constants — the `intent`
string parameter was used for rct7_steps/graphrag/crystal below it, but
never actually reached the FDIA computation at all, despite FDIA being the
one component with real, meaningful math (F = D^I * A). These tests lock in
the fix: synthesize_fdia_inputs() derives real D/I from intent_compiler.py's
actual compiled IntentObject (risk_profile, scope_type, validation result,
constraint count), not fixed numbers.
"""

from __future__ import annotations

import pytest

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


@pytest.fixture()
def kernel() -> AlgorithmKernel41:
    return AlgorithmKernel41()


class TestFdiaSynthesis:
    def test_different_intents_produce_different_real_di_pairs(self, kernel):
        low_risk = kernel.synthesize_fdia_inputs("analyze the quarterly revenue report")
        high_risk = kernel.synthesize_fdia_inputs("deploy the new microservice to production infrastructure")
        assert low_risk[:2] != high_risk[:2], "D/I must not collapse to the same fixed pair regardless of input"

    def test_higher_risk_and_broader_scope_intent_gets_a_stricter_intent_precision(self, kernel):
        low = kernel.synthesize_fdia_inputs("analyze the quarterly revenue report")
        high = kernel.synthesize_fdia_inputs("deploy the new microservice to production infrastructure")
        assert high[1] > low[1], "SYSTEMIC/INFRASTRUCTURE intent must demand a higher (stricter) I than a LOW-risk analysis intent"

    def test_intent_precision_stays_in_documented_range(self, kernel):
        for text in ["analyze x", "deploy y to production infrastructure", "refactor the auth module", "asdkjaslkdj gibberish"]:
            _, I, _ = kernel.synthesize_fdia_inputs(text)
            assert 0.5 <= I <= 2.0, f"I={I} out of documented [0.5, 2.0] range for {text!r}"

    def test_data_quality_stays_in_documented_range(self, kernel):
        for text in ["analyze x", "deploy y to production infrastructure", "asdkjaslkdj gibberish"]:
            D, _, _ = kernel.synthesize_fdia_inputs(text)
            assert 0.1 <= D <= 1.0, f"D={D} out of documented [0.1, 1.0] range for {text!r}"

    def test_unclassifiable_intent_falls_back_to_a_low_documented_pair_not_a_crash(self, kernel):
        D, I, result = kernel.synthesize_fdia_inputs("asdkjaslkdj random unclassifiable gibberish text")
        assert result.intent is None, "setup assumption: this text must genuinely fail to classify"
        assert D == 0.3
        assert I == 0.5

    def test_pipeline_no_longer_hardcodes_098_096(self, kernel):
        """Regression test for the exact bug found: algo_01_fdia(0.98, 0.96, 1.0) called regardless of `intent`."""
        result = kernel.process_intent_full_pipeline("asdkjaslkdj random unclassifiable gibberish text")
        assert result["fdia_inputs"]["data_quality"] != 0.98
        assert result["fdia_inputs"]["intent_precision"] != 0.96
        assert result["fdia_inputs"]["intent_classified"] is False

    def test_pipeline_fdia_inputs_reflect_real_classification_for_a_normal_intent(self, kernel):
        result = kernel.process_intent_full_pipeline("analyze the quarterly revenue report and summarize key trends")
        assert result["fdia_inputs"]["intent_classified"] is True
        assert result["fdia_inputs"]["intent_type"] == "ANALYZE_RISK"

    def test_fdia_score_still_computed_via_the_real_algo_01_fdia_formula(self, kernel):
        result = kernel.process_intent_full_pipeline("asdkjaslkdj random unclassifiable gibberish text")
        # D=0.3, I=0.5, A=1.0 -> F = 0.3^0.5 = 0.5477225575...
        assert result["fdia_score"] == pytest.approx(0.5477, abs=1e-4)
