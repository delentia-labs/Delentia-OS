"""
Real CapabilityRegistry tests — Round 26 Phase 20 Task 42.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.capability_registry import CapabilityRegistry


def test_dependency_is_resolved_before_the_dependent_and_result_is_a_real_singleton():
    registry = CapabilityRegistry()
    build_log = []

    def build_dep():
        build_log.append("dep")
        return {"name": "dep"}

    def build_main():
        build_log.append("main")
        return {"name": "main"}

    registry.register("dep", build_dep)
    registry.register("main", build_main, depends_on=["dep"])

    first = registry.get("main")
    second = registry.get("main")

    assert build_log == ["dep", "main"], f"dependency must be resolved before the dependent; got {build_log}"
    assert first is second, "get() must return the same cached instance, not re-construct it"


def test_circular_dependency_raises_a_clear_error_instead_of_infinite_recursion():
    registry = CapabilityRegistry()
    registry.register("a", lambda: {"name": "a"}, depends_on=["b"])
    registry.register("b", lambda: {"name": "b"}, depends_on=["a"])

    with pytest.raises(ValueError, match="circular"):
        registry.get("a")


def test_unregistered_capability_raises_a_clear_keyerror():
    registry = CapabilityRegistry()
    with pytest.raises(KeyError):
        registry.get("does_not_exist")


def test_kernel_get_capability_wraps_the_real_already_constructed_engine_not_a_duplicate(shared_kernel):
    # Round 29 Phase 33 Task 65: migrated onto shared_kernel - a pure
    # identity check, unaffected by any other test's kernel usage.
    resolved = shared_kernel.get_capability("graphrag_engine")

    assert resolved is shared_kernel._graphrag_engine, "registry must return the SAME real instance, not a second copy"
