"""
rct_control_plane/tests/conftest.py — Round 28 Phase 28 Task 55.

Round 27's engineering audit found 22/77 test files construct a full real
AlgorithmKernel41() directly rather than sharing one instance, each paying
the real per-instance construction cost. This adds a genuinely shared,
session-scoped fixture as an OPT-IN for new tests. It deliberately does
NOT retrofit any of the 22 existing files — several may rely on a fresh
kernel's per-test-isolated executed_counts/engine state, and verifying
that individually for all 22 is real, separate work (Round 29 candidate),
not something to do blindly in the same task that introduces the fixture.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


@pytest.fixture(scope="session")
def shared_kernel() -> AlgorithmKernel41:
    """A real, genuinely shared AlgorithmKernel41 instance for tests that
    don't need per-test isolation of kernel state. Session-scoped: built
    once for the whole pytest run, not once per test."""
    return AlgorithmKernel41()
