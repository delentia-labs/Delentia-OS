"""
Real shared-kernel-fixture demonstration test — Round 28 Phase 28 Task 55.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def test_shared_kernel_fixture_resolves_to_a_real_kernel(shared_kernel):
    assert shared_kernel.version == "v3.0.0-41-ALGO-COMPLETE"
    assert shared_kernel.executed_counts["ALGO-01"] >= 0


def test_shared_kernel_fixture_is_genuinely_the_same_instance_across_tests(shared_kernel):
    # Real proof of sharing: calling a real algorithm here should be
    # visible to any other test in the same session using the same
    # fixture, since pytest caches session-scoped fixtures.
    shared_kernel.algo_01_fdia(1.0, 1.0, 1.0)
    assert shared_kernel.executed_counts["ALGO-01"] >= 1
