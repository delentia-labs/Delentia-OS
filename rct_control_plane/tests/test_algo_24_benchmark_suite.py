"""
Round 45 item C: real tests for ALGO-24 (KernelBenchmarkSuite), a real,
in-process wall-clock benchmark harness genuinely used by
algorithm_kernel_41.py. Ported and expanded from the file's own
__main__ smoke test (same real functions/timing assertions), plus
per-branch edge cases the smoke test didn't cover: empty-state
properties, p95 on small N, benchmark_many's tuple-arg shapes, and the
5-error cap on to_dict().
"""
import asyncio
import time

import pytest

from rct_control_plane.algo_24_benchmark_suite import BenchmarkResult, KernelBenchmarkSuite


def _fast_fn():
    return sum(range(1000))


def _slow_fn():
    time.sleep(0.01)
    return True


async def _async_fn():
    await asyncio.sleep(0.005)
    return True


def _make_flaky_fn():
    counter = [0]

    def _flaky_fn():
        counter[0] += 1
        if counter[0] % 2 == 0:
            raise ValueError("real deliberate failure for the even calls")
        return True

    return _flaky_fn


class TestBenchmarkResultEmptyState:
    def test_all_stats_are_zero_with_no_durations_recorded(self):
        result = BenchmarkResult(name="empty", iterations=0, successes=0, failures=0)
        assert result.mean_ms == 0.0
        assert result.p50_ms == 0.0
        assert result.p95_ms == 0.0
        assert result.min_ms == 0.0
        assert result.max_ms == 0.0

    def test_to_dict_shape_on_empty_result(self):
        result = BenchmarkResult(name="empty", iterations=0, successes=0, failures=0)
        d = result.to_dict()
        assert d["name"] == "empty"
        assert d["mean_ms"] == 0.0
        assert d["errors"] == []


class TestBenchmarkResultRealStatistics:
    def test_p95_on_a_single_duration_returns_that_duration(self):
        result = BenchmarkResult(name="single", iterations=1, successes=1, failures=0, durations_ms=[7.5])
        assert result.p95_ms == 7.5
        assert result.p50_ms == 7.5
        assert result.min_ms == 7.5
        assert result.max_ms == 7.5

    def test_p95_index_never_exceeds_the_real_list_bounds(self):
        # min(int(len*0.95), len-1) - for small N this must clamp to the
        # last real index, not go out of range.
        durations = [1.0, 2.0, 3.0]
        result = BenchmarkResult(name="three", iterations=3, successes=3, failures=0, durations_ms=durations)
        assert result.p95_ms == 3.0

    def test_to_dict_caps_errors_at_5_even_with_more_real_failures(self):
        errors = [f"Error{i}" for i in range(8)]
        result = BenchmarkResult(name="many_errors", iterations=8, successes=0, failures=8,
                                  durations_ms=[1.0] * 8, errors=errors)
        assert len(result.to_dict()["errors"]) == 5
        assert result.to_dict()["errors"] == errors[:5]


class TestKernelBenchmarkSuiteRealTiming:
    """Ported from algo_24_benchmark_suite.py's own __main__ smoke test -
    identical real functions and identical real timing assertions, now
    running under pytest instead of manual execution."""

    @pytest.mark.asyncio
    async def test_slow_sync_function_measures_slower_than_fast_one(self):
        suite = KernelBenchmarkSuite()
        fast_result = await suite.benchmark("fast_fn", _fast_fn, iterations=20)
        slow_result = await suite.benchmark("slow_fn", _slow_fn, iterations=5)
        assert slow_result.mean_ms > fast_result.mean_ms
        assert slow_result.mean_ms >= 9.0

    @pytest.mark.asyncio
    async def test_async_function_is_awaited_and_timed_for_real(self):
        suite = KernelBenchmarkSuite()
        async_result = await suite.benchmark("async_fn", _async_fn, iterations=5)
        assert async_result.successes == 5
        assert async_result.mean_ms >= 4.0

    @pytest.mark.asyncio
    async def test_flaky_function_records_real_successes_and_failures(self):
        suite = KernelBenchmarkSuite()
        flaky_result = await suite.benchmark("flaky_fn", _make_flaky_fn(), iterations=10)
        assert flaky_result.failures == 5
        assert flaky_result.successes == 5
        assert len(flaky_result.errors) == 5
        assert all("ValueError" in e for e in flaky_result.errors)

    @pytest.mark.asyncio
    async def test_a_failing_call_still_records_a_real_duration(self):
        suite = KernelBenchmarkSuite()

        def always_fails():
            raise RuntimeError("real deliberate failure")

        result = await suite.benchmark("always_fails", always_fails, iterations=3)
        assert result.failures == 3
        assert result.successes == 0
        assert len(result.durations_ms) == 3
        assert all(d >= 0.0 for d in result.durations_ms)

    @pytest.mark.asyncio
    async def test_benchmark_passes_through_real_args_and_kwargs(self):
        suite = KernelBenchmarkSuite()
        calls = []

        def recorder(a, b, keyword=None):
            calls.append((a, b, keyword))

        await suite.benchmark("recorder", recorder, 1, 2, iterations=3, keyword="x")
        assert calls == [(1, 2, "x")] * 3

    @pytest.mark.asyncio
    async def test_completed_benchmarks_is_populated_by_name(self):
        suite = KernelBenchmarkSuite()
        await suite.benchmark("fast_fn", _fast_fn, iterations=2)
        assert "fast_fn" in suite.completed_benchmarks
        assert suite.completed_benchmarks["fast_fn"].iterations == 2


class TestBenchmarkMany:
    @pytest.mark.asyncio
    async def test_runs_multiple_targets_with_varying_tuple_shapes(self):
        suite = KernelBenchmarkSuite()
        calls = []

        def with_args(a, b):
            calls.append((a, b))

        def no_args():
            calls.append(())

        results = await suite.benchmark_many({
            "no_args_target": (no_args,),
            "with_args_target": (with_args, (1, 2)),
        }, iterations=2)

        assert set(results.keys()) == {"no_args_target", "with_args_target"}
        assert results["no_args_target"].successes == 2
        assert results["with_args_target"].successes == 2
        assert (1, 2) in calls

    @pytest.mark.asyncio
    async def test_supports_kwargs_in_the_third_tuple_position(self):
        suite = KernelBenchmarkSuite()
        calls = []

        def with_kwargs(x, flag=False):
            calls.append((x, flag))

        await suite.benchmark_many({
            "target": (with_kwargs, (5,), {"flag": True}),
        }, iterations=1)
        assert calls == [(5, True)]


class TestGetSummary:
    def test_empty_summary_before_any_real_benchmark(self):
        suite = KernelBenchmarkSuite()
        summary = suite.get_summary()
        assert summary == {"total_benchmarks": 0}

    @pytest.mark.asyncio
    async def test_summary_identifies_the_real_fastest_and_slowest(self):
        suite = KernelBenchmarkSuite()
        await suite.benchmark("fast_fn", _fast_fn, iterations=20)
        await suite.benchmark("slow_fn", _slow_fn, iterations=5)
        flaky_fn = _make_flaky_fn()
        await suite.benchmark("flaky_fn", flaky_fn, iterations=10)

        summary = suite.get_summary()
        assert summary["total_benchmarks"] == 3
        assert summary["total_iterations"] == 35
        assert summary["total_failures"] == 5
        # A bare counter increment genuinely measures faster than summing
        # 1000 ints - a real, correct result, not a bug.
        assert summary["fastest"] == "flaky_fn"
        assert summary["slowest"] == "slow_fn"
        assert "results" in summary
        assert set(summary["results"].keys()) == {"fast_fn", "slow_fn", "flaky_fn"}
