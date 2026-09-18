"""
Real persistent cross-session memory tests — Round 21 Phase 4.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_mee_growth_state_survives_a_real_kernel_restart():
    kernel1 = AlgorithmKernel41()
    kernel1.algo_07_mee(growth_signal=0.9)  # real step, G moves from 1.0
    g_after_step = kernel1._mee_session_default.g
    assert g_after_step != 1.0

    # Simulate a real restart: brand new kernel instance, same persistence db
    kernel2 = AlgorithmKernel41()
    # MEESession.to_dict() (pre-existing, real code) rounds g_current to 6
    # decimal places for storage - so the restored value matches the
    # in-memory one only up to that real precision, not bit-for-bit.
    assert kernel2._mee_session_default.g == pytest.approx(g_after_step, abs=1e-6), (
        "a fresh kernel instance must resume the REAL persisted G, not reset to 1.0"
    )
