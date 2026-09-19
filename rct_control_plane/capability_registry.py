"""
CapabilityRegistry — Round 26 Phase 20 Task 42.

A scoped, ADDITIVE dependency-injection layer, not a rewrite of
AlgorithmKernel41.__init__. That constructor (algorithm_kernel_41.py:201-349)
is a real, tested, load-bearing ~150-line block directly instantiating 30+
engines — rewriting it into a full DI container was repeatedly deferred
across Rounds 23-25 as too high-risk for the benefit, and this round doesn't
attempt that either.

Instead, this gives FUTURE rounds a real, working, lazy-singleton lookup
mechanism that a new capability can register itself into, without requiring
a hand-edit of __init__ plus every call site that needs it — directly
addressing the friction Round 25's Task 35-36 selective-dispatch surfaced
(a new node had to be added in 3 separate places: __init__, the relevance
table, and the node_fns dict). Existing engines keep their existing
self._xxx attributes untouched (Zero-Delete); the registry wraps them as an
additional, parallel access path.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class CapabilityRegistry:
    """Real lazy-singleton capability lookup with dependency resolution."""

    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._depends_on: Dict[str, List[str]] = {}
        self._instances: Dict[str, Any] = {}

    def register(self, name: str, factory: Callable[[], Any], depends_on: Optional[List[str]] = None) -> None:
        self._factories[name] = factory
        self._depends_on[name] = depends_on or []

    def list_capabilities(self) -> List[str]:
        return list(self._factories.keys())

    def get(self, name: str) -> Any:
        return self._resolve(name, resolving=set())

    def _resolve(self, name: str, resolving: set) -> Any:
        if name in self._instances:
            return self._instances[name]

        if name not in self._factories:
            raise KeyError(f"capability '{name}' is not registered")

        if name in resolving:
            cycle = " -> ".join(list(resolving) + [name])
            raise ValueError(f"circular capability dependency detected: {cycle}")

        resolving = resolving | {name}
        for dep_name in self._depends_on[name]:
            self._resolve(dep_name, resolving=resolving)

        instance = self._factories[name]()
        self._instances[name] = instance
        return instance
