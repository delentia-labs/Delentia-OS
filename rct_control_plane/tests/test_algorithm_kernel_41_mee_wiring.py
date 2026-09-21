"""
Regression tests for wiring ALGO-07 (MEE v2) into AlgorithmKernel41.

Context: an audit on 2026-09-12 found mee_engine.py had real, tested logic
(MEEEngine/MEESession implementing G(t+1) = G(t)×(1+MΔ)×R_t) that was never
imported or called from anywhere in the codebase — algorithm_kernel_41.py's
own docstring named "ALGO-07 (MEE v2)" while listing it in
NOT_IMPLEMENTED_ALGO_IDS. These tests lock in the fix: a real algo_07_mee()
method backed by an actual MEEEngine session, wired into
process_intent_full_pipeline().
"""

from __future__ import annotations

import pytest

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


@pytest.fixture()
def kernel() -> AlgorithmKernel41:
    """A fresh kernel per test — the module-level ALGORITHM_KERNEL singleton
    accumulates MEE growth across the whole test session, which would make
    tests order-dependent.

    Round 39: a fresh AlgorithmKernel41() object is NOT enough on its own -
    real, confirmed via direct reproduction after an extensive real-testing
    session: __init__ restores _mee_session_default from the real, shared,
    on-disk `rct_control_plane_agentic.db` (this is the genuine cross-
    session MEE persistence mechanism, working exactly as designed - see
    the Round 38 RCTDB/MEE investigation), so a "fresh kernel" still
    inherits whatever G the real database has accumulated from every OTHER
    real pipeline call across this whole test session. After enough real
    testing, G legitimately reaches its own cap (1000.0), and this test's
    "G must evolve" assertion fails not because growth is broken, but
    because it's genuinely saturated. Reset the in-memory session (both the
    engine's own session dict and the cached default reference point to the
    SAME object) to a real fresh one, matching exactly what __init__ builds
    when no persisted row exists - without touching the shared db file
    itself (other real cross-session-persistence tests still need it)."""
    from rct_control_plane.mee_engine import MEESession

    kernel = AlgorithmKernel41()
    # NOT mee_engine.create_session() - it raises ValueError for a
    # session_id that already exists (real, confirmed via direct check
    # of its source), and __init__ already registered "kernel_default".
    # Constructs a session directly with the same real defaults
    # create_session() itself would have used.
    fresh_session = MEESession("kernel_default")
    kernel._mee_engine._sessions["kernel_default"] = fresh_session
    kernel._mee_session_default = fresh_session
    return kernel


class TestAlgo07Wiring:
    def test_algo_07_is_no_longer_reported_as_unimplemented(self, kernel):
        assert "ALGO-07" in kernel.IMPLEMENTED_ALGO_IDS
        assert "ALGO-07" not in kernel.NOT_IMPLEMENTED_ALGO_IDS
        # Total must still be 41 designed IDs across all three categories
        # (IMPLEMENTED_ALGO_IDS, NEWLY_WIRED_ALGO_IDS since Round 19 Phase 1,
        # and NOT_IMPLEMENTED_ALGO_IDS) — moving one between them must not
        # silently drop or duplicate an ID.
        assert (
            len(kernel.IMPLEMENTED_ALGO_IDS)
            + len(kernel.NEWLY_WIRED_ALGO_IDS)
            + len(kernel.NOT_IMPLEMENTED_ALGO_IDS)
        ) == 41

    def test_algo_07_mee_advances_real_growth_state_not_a_fixed_return(self, kernel):
        first = kernel.algo_07_mee(growth_signal=0.3)
        second = kernel.algo_07_mee(growth_signal=0.3)
        assert first["g_after"] != second["g_after"], "G must evolve across successive calls, not return a constant"
        assert second["g_before"] == first["g_after"], "each step must continue from the previous step's result"
        assert kernel.executed_counts["ALGO-07"] == 2

    def test_algo_07_mee_governance_violation_reduces_resilience(self, kernel):
        clean = kernel.algo_07_mee(growth_signal=0.1, governance_violation=False)
        violated = kernel.algo_07_mee(growth_signal=0.1, governance_violation=True)
        assert violated["resilience"] < clean["resilience"]

    def test_pipeline_run_includes_a_real_mee_step_and_summary(self, kernel):
        result = kernel.process_intent_full_pipeline("analyze the quarterly revenue report")
        assert "mee_step" in result
        assert "mee_growth_summary" in result
        assert result["mee_step"]["step"] == 1
        assert result["mee_growth_summary"]["steps"] == 1
        # growth_signal is derived from this run's real FDIA score (fdia_score - 0.5)
        assert result["mee_step"]["delta"] == pytest.approx(result["fdia_score"] - 0.5, abs=1e-6)

    def test_pipeline_growth_accumulates_across_successive_runs(self, kernel):
        r1 = kernel.process_intent_full_pipeline("first intent")
        r2 = kernel.process_intent_full_pipeline("second intent")
        assert r2["mee_step"]["g_before"] == r1["mee_step"]["g_after"]
        assert r2["mee_growth_summary"]["steps"] == 2
