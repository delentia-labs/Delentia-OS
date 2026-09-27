"""
Round 45 item C (test coverage continuation): real tests for ALGO-28's
ConnectionPool and RequestBatcher - 0% coverage before this file. Real
asyncio.Semaphore/Lock, real deque-based pooling/batching, real timing
logic (TTL, idle timeout, batch windows) all exercised for real. Following
this module's own docstring (and the source repo's own test_cio.py
precedent it cites), the ONE thing mocked is the actual socket I/O -
`httpx.AsyncClient.request` - via unittest.mock.patch.object at the class
level; everything else (pool/batcher internals) runs for real.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from rct_control_plane.algo_28_cio import (
    ConnectionPool, PoolConfig, HealthStatus,
    RequestBatcher, HTTPRequest, Priority,
)


def _fake_response(status_code=200):
    return httpx.Response(status_code=status_code, request=httpx.Request("GET", "https://example.com"))


@pytest.fixture
def mocked_request():
    """Patches httpx.AsyncClient.request at the class level - real
    Connection/ConnectionPool code paths run, only the socket I/O is
    faked, matching this module's own docstring precedent."""
    with patch.object(httpx.AsyncClient, "request", new=AsyncMock(return_value=_fake_response())) as m:
        yield m


class TestConnectionPoolLifecycle:
    @pytest.mark.asyncio
    async def test_start_warms_up_to_min_size(self):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=3, max_size=10))
        await pool.start()
        try:
            status = pool.get_status()
            assert status.idle == 3
            assert status.created_connections == 3
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=2, max_size=10))
        await pool.start()
        try:
            await pool.start()  # second call must be a no-op, not double-warm
            assert pool.get_status().created_connections == 2
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_all_connections_and_cancels_maintenance(self):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=2, max_size=10))
        await pool.start()
        await pool.stop()
        assert pool.get_status().idle == 0
        assert pool._maintenance_task.cancelled() or pool._maintenance_task.done()

    @pytest.mark.asyncio
    async def test_stop_before_start_is_a_safe_no_op(self):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=1, max_size=10))
        await pool.stop()  # must not raise


class TestConnectionPoolAcquire:
    @pytest.mark.asyncio
    async def test_acquire_reuses_a_warmed_connection(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=1, max_size=10))
        await pool.start()
        try:
            async with pool.acquire() as conn:
                response = await conn.execute_request("GET", "https://example.com")
            assert response.status_code == 200
            status = pool.get_status()
            assert status.reuse_rate == 1.0  # the one warmed connection was reused, not newly created
            assert status.created_connections == 1
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_acquire_creates_a_new_connection_when_pool_is_empty(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=0, max_size=10))
        await pool.start()
        try:
            async with pool.acquire() as conn:
                await conn.execute_request("GET", "https://example.com")
            assert pool.get_status().created_connections == 1
            assert pool.get_status().reuse_rate == 0.0
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_connection_returns_to_pool_after_healthy_use(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=1, max_size=10))
        await pool.start()
        try:
            async with pool.acquire() as conn:
                await conn.execute_request("GET", "https://example.com")
            status = pool.get_status()
            assert status.idle == 1
            assert status.active == 0
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_connection_that_errored_is_closed_not_returned_to_pool(self):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=1, max_size=10))
        await pool.start()
        try:
            with patch.object(httpx.AsyncClient, "request", new=AsyncMock(side_effect=httpx.ConnectError("boom"))):
                with pytest.raises(httpx.ConnectError):
                    async with pool.acquire() as conn:
                        await conn.execute_request("GET", "https://example.com")
            status = pool.get_status()
            # The unhealthy connection was closed on release, not pooled.
            assert status.idle == 0
            assert status.active == 0
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_expired_connection_is_not_reused_and_gets_replaced(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=1, max_size=10, ttl_seconds=1))
        await pool.start()
        try:
            # Force the warmed connection to look expired without a real sleep.
            pool._pool[0].created_at = time.time() - 10
            async with pool.acquire() as conn:
                await conn.execute_request("GET", "https://example.com")
            # A fresh connection was created since the pooled one was expired.
            assert pool.get_status().created_connections == 2
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrent_acquisitions_to_max_size(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p1", min_size=0, max_size=1))
        await pool.start()
        try:
            entered_second = False

            async def _hold_then_release():
                async with pool.acquire():
                    await asyncio.sleep(0.05)

            async def _try_second():
                nonlocal entered_second
                async with pool.acquire():
                    entered_second = True

            first = asyncio.create_task(_hold_then_release())
            await asyncio.sleep(0.01)  # let the first task actually acquire
            second = asyncio.create_task(_try_second())
            await asyncio.sleep(0.02)
            assert entered_second is False  # still blocked by max_size=1
            await asyncio.gather(first, second)
            assert entered_second is True  # eventually got in after release
        finally:
            await pool.stop()


class TestConnectionExpiryChecks:
    def test_ttl_zero_means_never_expires(self):
        from rct_control_plane.algo_28_cio import Connection
        c = Connection(client=None, pool_name="p")
        c.created_at = time.time() - 999999
        assert c.is_expired(ttl=0) is False

    def test_positive_ttl_expires_after_age_exceeds_it(self):
        from rct_control_plane.algo_28_cio import Connection
        c = Connection(client=None, pool_name="p")
        c.created_at = time.time() - 100
        assert c.is_expired(ttl=10) is True
        assert c.is_expired(ttl=1000) is False

    def test_idle_timeout_checks_last_used_at(self):
        from rct_control_plane.algo_28_cio import Connection
        c = Connection(client=None, pool_name="p")
        c.last_used_at = time.time() - 100
        assert c.is_idle_timeout(timeout=10) is True
        assert c.is_idle_timeout(timeout=1000) is False


class TestConnectionPoolHealthStatus:
    def test_healthy_when_no_errors_and_low_utilization(self):
        pool = ConnectionPool(PoolConfig(name="p", min_size=2, max_size=10))
        pool._created_count = 10
        pool._failed_count = 0
        for _ in range(2):
            pool._pool.append(object())  # size just needs len(), not real Connections
        pool._update_health_status()
        assert pool._health_status == HealthStatus.HEALTHY

    def test_unhealthy_when_error_rate_above_half(self):
        pool = ConnectionPool(PoolConfig(name="p", min_size=2, max_size=10))
        pool._created_count = 10
        pool._failed_count = 6
        pool._update_health_status()
        assert pool._health_status == HealthStatus.UNHEALTHY

    def test_unhealthy_when_pool_size_below_half_min(self):
        pool = ConnectionPool(PoolConfig(name="p", min_size=10, max_size=20))
        pool._created_count = 1
        pool._failed_count = 0
        # pool_size (0) < min_size // 2 (5)
        pool._update_health_status()
        assert pool._health_status == HealthStatus.UNHEALTHY

    def test_degraded_when_utilization_above_90_percent(self):
        pool = ConnectionPool(PoolConfig(name="p", min_size=1, max_size=10))
        pool._created_count = 10
        pool._failed_count = 0
        # utilization = in_use / max_size must be STRICTLY > 0.9 - 9/10
        # is exactly 0.9 and does not trigger the "> 0.9" check, so this
        # uses 10 in_use (utilization 1.0) instead.
        for _ in range(10):
            pool._in_use.add(object())
        pool._update_health_status()
        assert pool._health_status == HealthStatus.DEGRADED


class TestConnectionPoolResizeAndFlush:
    @pytest.mark.asyncio
    async def test_resize_up_releases_additional_semaphore_slots(self):
        pool = ConnectionPool(PoolConfig(name="p", min_size=0, max_size=2))
        await pool.start()
        try:
            await pool.resize(new_min=0, new_max=5)
            assert pool.config.max_size == 5
            # 3 extra permits were released - acquiring 5 concurrently must not block.
            acquired = 0
            for _ in range(5):
                await pool._semaphore.acquire()
                acquired += 1
            assert acquired == 5
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_flush_closes_pooled_connections_and_rewarms(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p", min_size=2, max_size=10))
        await pool.start()
        try:
            old_connections = list(pool._pool)
            await pool.flush()
            assert len(pool._pool) == 2  # re-warmed back to min_size
            assert all(c not in pool._pool for c in old_connections)  # old ones really replaced
        finally:
            await pool.stop()


class TestRequestBatcherPriorityBypass:
    @pytest.mark.asyncio
    async def test_critical_priority_bypasses_batching_entirely(self):
        batcher = RequestBatcher(batch_window_ms=10, min_batch_size=2)
        calls = []

        async def processor(req):
            calls.append(req.url)
            return "critical-result"

        result = await batcher.submit(
            HTTPRequest(url="https://x", priority=Priority.CRITICAL), processor,
        )
        assert result == "critical-result"
        assert calls == ["https://x"]
        assert batcher.get_stats()["requests_bypassed"] == 1
        assert batcher.get_stats()["requests_batched"] == 0

    @pytest.mark.asyncio
    async def test_queue_full_forces_bypass_even_for_normal_priority(self):
        batcher = RequestBatcher(batch_window_ms=10, min_batch_size=2, max_queue_depth=0)

        async def processor(req):
            return "bypassed"

        result = await batcher.submit(HTTPRequest(url="https://x"), processor)
        assert result == "bypassed"
        assert batcher.get_stats()["requests_bypassed"] == 1


class TestRequestBatcherRealBatchingFlow:
    @pytest.mark.asyncio
    async def test_normal_priority_request_is_genuinely_batched_and_resolves_with_the_real_processor_result(self):
        """Regression test for the disclosed 2026-09-14 upstream fix (see
        module docstring): a batched request must resolve to whatever the
        real processor computed, not a placeholder None."""
        batcher = RequestBatcher(batch_window_ms=5, min_batch_size=1, max_batch_size=10)
        await batcher.start()
        try:
            async def processor(req):
                return f"processed:{req.url}"

            result = await asyncio.wait_for(
                batcher.submit(HTTPRequest(url="https://real-result-check"), processor),
                timeout=5.0,
            )
            assert result == "processed:https://real-result-check"
            # submit()'s future resolves inside _process_single(), which
            # runs concurrently with _process_batch()'s own stat-increment
            # code (a separate coroutine on the same event loop) - a real
            # race, not a bug: the caller's future can resolve a tick
            # before _process_batch() finishes updating its counters.
            # Yield once so that already-scheduled continuation runs.
            await asyncio.sleep(0.02)
            assert batcher.get_stats()["requests_batched"] == 1
        finally:
            await batcher.stop()

    @pytest.mark.asyncio
    async def test_processor_exception_propagates_to_the_caller_not_swallowed(self):
        batcher = RequestBatcher(batch_window_ms=5, min_batch_size=1, max_batch_size=10)
        await batcher.start()
        try:
            async def failing_processor(req):
                raise ValueError("real processor failure")

            with pytest.raises(ValueError, match="real processor failure"):
                await asyncio.wait_for(
                    batcher.submit(HTTPRequest(url="https://will-fail"), failing_processor),
                    timeout=5.0,
                )
        finally:
            await batcher.stop()

    @pytest.mark.asyncio
    async def test_multiple_requests_to_same_url_are_grouped_in_one_batch(self):
        batcher = RequestBatcher(batch_window_ms=20, min_batch_size=3, max_batch_size=10)
        await batcher.start()
        try:
            call_log = []

            async def processor(req):
                call_log.append(req.url)
                return req.url

            results = await asyncio.wait_for(
                asyncio.gather(*[
                    batcher.submit(HTTPRequest(url="https://same"), processor) for _ in range(3)
                ]),
                timeout=5.0,
            )
            assert results == ["https://same"] * 3
            assert len(call_log) == 3
            await asyncio.sleep(0.02)  # see the same race note above
            assert batcher.get_stats()["batches_processed"] >= 1
        finally:
            await batcher.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_pending_futures_for_unbatched_requests(self):
        batcher = RequestBatcher(batch_window_ms=10_000, min_batch_size=100)  # window long enough it never fires
        await batcher.start()

        async def processor(req):
            return "never called"

        submit_task = asyncio.create_task(
            batcher.submit(HTTPRequest(url="https://stuck"), processor)
        )
        await asyncio.sleep(0.02)  # let it actually queue
        await batcher.stop()

        with pytest.raises(asyncio.CancelledError):
            await submit_task


class TestCollectBatchDirectly:
    """_collect_batch()'s min-size/max-wait logic is timing-sensitive - unit
    tested directly against a real batcher instance (not via the
    background _batch_processor loop) for deterministic, fast assertions."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_below_min_size_and_within_wait_window(self):
        batcher = RequestBatcher(batch_window_ms=10, min_batch_size=5)
        item = _make_batch_item(batcher, "https://x")
        batcher._queues[Priority.NORMAL].append(item)

        batch = await batcher._collect_batch()
        assert batch == []
        # The item was put back, not lost.
        assert item in batcher._queues[Priority.NORMAL]

    @pytest.mark.asyncio
    async def test_returns_batch_once_min_size_is_reached(self):
        batcher = RequestBatcher(batch_window_ms=10, min_batch_size=2)
        for _ in range(2):
            batcher._queues[Priority.NORMAL].append(_make_batch_item(batcher, "https://x"))

        batch = await batcher._collect_batch()
        assert len(batch) == 2

    @pytest.mark.asyncio
    async def test_returns_batch_after_max_wait_even_below_min_size(self):
        batcher = RequestBatcher(batch_window_ms=10, min_batch_size=99)
        item = _make_batch_item(batcher, "https://x")
        item.queued_at = time.time() - 1.0  # far past the 50ms max-wait override
        batcher._queues[Priority.NORMAL].append(item)

        batch = await batcher._collect_batch()
        assert batch == [item]

    @pytest.mark.asyncio
    async def test_higher_priority_queues_are_drained_before_lower_ones(self):
        batcher = RequestBatcher(batch_window_ms=10, min_batch_size=1, max_batch_size=1)
        low_item = _make_batch_item(batcher, "https://low")
        high_item = _make_batch_item(batcher, "https://high")
        batcher._queues[Priority.LOW].append(low_item)
        batcher._queues[Priority.HIGH].append(high_item)

        batch = await batcher._collect_batch()
        assert batch == [high_item]  # HIGH drained before LOW per Priority enum order


def _make_batch_item(batcher, url):
    from rct_control_plane.algo_28_cio import BatchItem
    return BatchItem(
        request=HTTPRequest(url=url), future=asyncio.get_event_loop().create_future(),
        priority=Priority.NORMAL, queued_at=time.time(),
    )


class TestAdaptParameters:
    def test_widens_window_when_efficiency_below_target(self):
        batcher = RequestBatcher(batch_window_ms=10, max_batch_size=100)
        batcher._batch_sizes.extend([10, 10, 10])  # 10% efficiency, well below 70% target
        batcher._current_window_ms = 10
        batcher._adapt_parameters()
        assert batcher._current_window_ms > 10

    def test_narrows_window_when_efficiency_above_95_percent(self):
        batcher = RequestBatcher(batch_window_ms=20, max_batch_size=10)
        batcher._batch_sizes.extend([10, 10, 10])  # 100% efficiency
        batcher._current_window_ms = 20
        batcher._adapt_parameters()
        assert batcher._current_window_ms < 20

    def test_no_op_with_no_batch_history_yet(self):
        batcher = RequestBatcher(batch_window_ms=10)
        window_before = batcher._current_window_ms
        batcher._adapt_parameters()
        assert batcher._current_window_ms == window_before

    def test_shrinks_batch_size_when_processing_is_slow(self):
        batcher = RequestBatcher(batch_window_ms=10, min_batch_size=1, max_batch_size=100)
        batcher._current_batch_size = 100
        batcher._batch_sizes.append(50)
        batcher._batch_times.append(10.0)  # way over target_time (10ms window -> 0.01s)
        batcher._adapt_parameters()
        assert batcher._current_batch_size < 100


class TestBatcherStats:
    def test_get_stats_shape_and_ratio_math(self):
        batcher = RequestBatcher(batch_window_ms=10, max_batch_size=10)
        batcher._requests_batched = 6
        batcher._requests_bypassed = 4
        stats = batcher.get_stats()
        assert stats["total_requests"] == 10
        assert stats["batch_ratio"] == 0.6
        assert set(stats["queued"].keys()) == {p.value for p in Priority}

    def test_get_stats_with_no_traffic_yet_has_zero_ratios_not_a_crash(self):
        batcher = RequestBatcher(batch_window_ms=10)
        stats = batcher.get_stats()
        assert stats["total_requests"] == 0
        assert stats["batch_ratio"] == 0
        assert stats["avg_batch_size"] == 0


class TestPerformMaintenanceDirectly:
    """_perform_maintenance() is normally only reached via the real
    background loop's `await asyncio.sleep(10)` - called directly here so
    its real eviction/top-up/health-status logic is exercised without a
    10-second test."""

    @pytest.mark.asyncio
    async def test_evicts_expired_connections_and_tops_back_up_to_min_size(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p", min_size=2, max_size=10, ttl_seconds=1))
        await pool.start()
        try:
            pool._pool[0].created_at = time.time() - 100  # force-expire one
            await pool._perform_maintenance()
            assert pool.get_status().idle == 2  # evicted one, topped back up to min_size
            assert pool.get_status().created_connections == 3  # 2 warmup + 1 replacement
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_no_op_when_nothing_is_expired_and_pool_is_already_full(self, mocked_request):
        pool = ConnectionPool(PoolConfig(name="p", min_size=1, max_size=10))
        await pool.start()
        try:
            await pool._perform_maintenance()
            assert pool.get_status().idle == 1
            assert pool.get_status().created_connections == 1  # no extra connections created
        finally:
            await pool.stop()


class TestConnectionCreationFailure:
    @pytest.mark.asyncio
    async def test_create_connection_failure_is_counted_and_returns_none(self, monkeypatch):
        pool = ConnectionPool(PoolConfig(name="p", min_size=0, max_size=10))

        def _boom(*a, **k):
            raise RuntimeError("simulated httpx.AsyncClient construction failure")
        monkeypatch.setattr(httpx, "AsyncClient", _boom)

        conn = await pool._create_connection()
        assert conn is None
        assert pool._failed_count == 1

    @pytest.mark.asyncio
    async def test_acquire_raises_when_the_pool_cannot_create_a_replacement(self, monkeypatch):
        pool = ConnectionPool(PoolConfig(name="p", min_size=0, max_size=10))
        await pool.start()

        def _boom(*a, **k):
            raise RuntimeError("simulated httpx.AsyncClient construction failure")
        monkeypatch.setattr(httpx, "AsyncClient", _boom)

        with pytest.raises(RuntimeError, match="Failed to acquire connection"):
            async with pool.acquire():
                pass


class TestResizeDown:
    @pytest.mark.asyncio
    async def test_resize_down_reduces_available_semaphore_permits(self):
        pool = ConnectionPool(PoolConfig(name="p", min_size=0, max_size=5))
        await pool.start()
        try:
            await pool.resize(new_min=0, new_max=2)
            assert pool.config.max_size == 2
            # Only 2 concurrent acquisitions should now fit without blocking.
            await pool._semaphore.acquire()
            await pool._semaphore.acquire()
            assert pool._semaphore.locked()
        finally:
            await pool.stop()


class TestBatcherStartStopIdempotency:
    @pytest.mark.asyncio
    async def test_start_twice_does_not_spawn_a_second_processor_task(self):
        batcher = RequestBatcher(batch_window_ms=10_000)
        await batcher.start()
        try:
            first_task = batcher._processor_task
            await batcher.start()
            assert batcher._processor_task is first_task
        finally:
            await batcher.stop()

    @pytest.mark.asyncio
    async def test_stop_before_start_is_a_safe_no_op(self):
        batcher = RequestBatcher(batch_window_ms=10)
        await batcher.stop()  # must not raise

    @pytest.mark.asyncio
    async def test_stop_twice_is_safe(self):
        batcher = RequestBatcher(batch_window_ms=10_000)
        await batcher.start()
        await batcher.stop()
        await batcher.stop()  # must not raise a second time
