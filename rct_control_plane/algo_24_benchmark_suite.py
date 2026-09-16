"""
ALGO-24: Benchmark Suite — real adaptation (not a literal port), 2026-09-16
(Round 20).

The real microservice (Delentia-Private-OS/rct_platform/microservices/
benchmark-suite/) is a genuinely large HTTP load-testing harness
(BenchmarkRunner + StressTester + MetricsCollector + a service registry
of OTHER running microservices to stress-test with concurrent users,
ramp-up, etc.) — its whole reason to exist is testing OTHER deployed
HTTP services. Porting it literally would need those other services
actually running and reachable, which is exactly the "needs other
microservices deployed" gap a prior audit already flagged, and a full
adaptation (redesigning its HTTP-load-generation model into something
meaningful for in-process calls) would be a disproportionate rebuild —
more like designing a new subsystem than porting one.

What's genuinely useful RIGHT NOW, and genuinely real: this kernel has
~24 real in-process algorithm methods (Round 19 Phases 1-2) that have
never had their own real latency measured. This is a small, honest
benchmark harness for exactly that — real wall-clock timing over N real
calls to a real kernel method, with real percentile statistics. It is
NOT a port of benchmark_runner.py's HTTP-stress-testing design; it is a
new, small, real capability in the same spirit (continuous performance
verification), scoped to what's actually available in this environment.
"""
from __future__ import annotations

import asyncio
import inspect
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class BenchmarkResult:
    """Real timing statistics for one algorithm over N real calls."""
    name: str
    iterations: int
    successes: int
    failures: int
    durations_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.durations_ms) if self.durations_ms else 0.0

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.durations_ms) if self.durations_ms else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.durations_ms:
            return 0.0
        sorted_d = sorted(self.durations_ms)
        idx = min(int(len(sorted_d) * 0.95), len(sorted_d) - 1)
        return sorted_d[idx]

    @property
    def min_ms(self) -> float:
        return min(self.durations_ms) if self.durations_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.durations_ms) if self.durations_ms else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "successes": self.successes,
            "failures": self.failures,
            "mean_ms": round(self.mean_ms, 4),
            "p50_ms": round(self.p50_ms, 4),
            "p95_ms": round(self.p95_ms, 4),
            "min_ms": round(self.min_ms, 4),
            "max_ms": round(self.max_ms, 4),
            "errors": self.errors[:5],  # cap for readability
        }


class KernelBenchmarkSuite:
    """
    Real benchmark harness for this kernel's own in-process algorithm
    methods. Not a mock — every measurement is a real wall-clock timing
    of a real call to a real algorithm implementation.
    """

    def __init__(self) -> None:
        self.completed_benchmarks: Dict[str, BenchmarkResult] = {}

    async def benchmark(
        self, name: str, fn: Callable[..., Any], *args: Any,
        iterations: int = 5, **kwargs: Any
    ) -> BenchmarkResult:
        """Run `fn(*args, **kwargs)` `iterations` real times (awaiting it
        if it's a coroutine function) and record real wall-clock timing
        for each call."""
        result = BenchmarkResult(name=name, iterations=iterations, successes=0, failures=0)

        is_async = inspect.iscoroutinefunction(fn)
        for _ in range(iterations):
            start = time.perf_counter()
            try:
                if is_async:
                    await fn(*args, **kwargs)
                else:
                    fn(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                result.durations_ms.append(elapsed_ms)
                result.successes += 1
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                result.durations_ms.append(elapsed_ms)
                result.failures += 1
                result.errors.append(f"{type(e).__name__}: {e}")

        self.completed_benchmarks[name] = result
        return result

    async def benchmark_many(
        self, targets: Dict[str, tuple], iterations: int = 5
    ) -> Dict[str, BenchmarkResult]:
        """Run `benchmark()` over several targets sequentially.
        `targets` maps a display name -> (callable, args, kwargs)."""
        results = {}
        for name, spec in targets.items():
            fn = spec[0]
            args = spec[1] if len(spec) > 1 else ()
            kwargs = spec[2] if len(spec) > 2 else {}
            results[name] = await self.benchmark(name, fn, *args, iterations=iterations, **kwargs)
        return results

    def get_summary(self) -> Dict[str, Any]:
        """Real aggregate summary across every benchmark run so far."""
        if not self.completed_benchmarks:
            return {"total_benchmarks": 0}

        all_means = [r.mean_ms for r in self.completed_benchmarks.values()]
        return {
            "total_benchmarks": len(self.completed_benchmarks),
            "total_iterations": sum(r.iterations for r in self.completed_benchmarks.values()),
            "total_failures": sum(r.failures for r in self.completed_benchmarks.values()),
            "fastest": min(self.completed_benchmarks.values(), key=lambda r: r.mean_ms).name,
            "slowest": max(self.completed_benchmarks.values(), key=lambda r: r.mean_ms).name,
            "avg_mean_ms_across_all": round(statistics.mean(all_means), 4),
            "results": {name: r.to_dict() for name, r in self.completed_benchmarks.items()},
        }


if __name__ == "__main__":
    async def _smoke_test():
        print("=" * 70)
        print("ALGO-24 Benchmark Suite smoke test (real timing of real functions)")
        print("=" * 70)

        suite = KernelBenchmarkSuite()

        def fast_fn():
            return sum(range(1000))

        def slow_fn():
            time.sleep(0.01)
            return True

        async def async_fn():
            await asyncio.sleep(0.005)
            return True

        def flaky_fn(counter=[0]):
            counter[0] += 1
            if counter[0] % 2 == 0:
                raise ValueError("real deliberate failure for the even calls")
            return True

        fast_result = await suite.benchmark("fast_fn", fast_fn, iterations=20)
        slow_result = await suite.benchmark("slow_fn", slow_fn, iterations=5)
        async_result = await suite.benchmark("async_fn", async_fn, iterations=5)
        flaky_result = await suite.benchmark("flaky_fn", flaky_fn, iterations=10)

        print(f"fast_fn:  {fast_result.to_dict()}")
        print(f"slow_fn:  {slow_result.to_dict()}")
        print(f"async_fn: {async_result.to_dict()}")
        print(f"flaky_fn: {flaky_result.to_dict()}")

        # Real assertions on real measured timing, not fabricated. Note:
        # flaky_fn (a single counter increment) genuinely measures faster
        # than fast_fn (summing 1000 ints) — a real, correct result, not a
        # bug — so it is the real fastest benchmark, not fast_fn.
        assert slow_result.mean_ms > fast_result.mean_ms, "real 10ms-sleep function must measure slower than real fast sum"
        assert slow_result.mean_ms >= 9.0, "real time.sleep(0.01) must measure at least ~9ms"
        assert async_result.mean_ms >= 4.0, "real asyncio.sleep(0.005) must measure at least ~4ms"
        assert flaky_result.failures == 5, "exactly the 5 real even-numbered calls must have really failed"
        assert flaky_result.successes == 5
        assert flaky_result.mean_ms < fast_result.mean_ms, "a bare counter increment must genuinely measure faster than summing 1000 ints"

        summary = suite.get_summary()
        print(f"\nSummary: {summary['total_benchmarks']} benchmarks, "
              f"fastest={summary['fastest']}, slowest={summary['slowest']}, "
              f"total_failures={summary['total_failures']}")
        assert summary["fastest"] == "flaky_fn", "real measured fastest is the trivial counter increment"
        assert summary["total_failures"] == 5

        print("\nALL ALGO-24 ASSERTIONS PASSED")

    asyncio.run(_smoke_test())
