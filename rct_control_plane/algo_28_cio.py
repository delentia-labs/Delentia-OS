"""
ALGO-28: CIO - Concurrent I/O Batching Optimizer (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/cio-optimizer/
app/optimizers/connection_pool.py and request_batcher.py on 2026-09-16,
following the same strip-the-FastAPI-keep-the-engine pattern used for
ALGO-15/16/18/19/20. Real async httpx connection pooling + real
priority-aware request batching - stdlib (asyncio, collections, dataclasses)
plus httpx (real AsyncClient pooling) and structlog (the source's own
logger). Both are importable in this environment (httpx 0.28.1,
structlog 25.5.0) but, like faiss-cpu for ALGO-16, are NOT declared in
Delentia-OS/pyproject.toml under any dependency group - same disclosed
DEPENDENCY GAP pattern as algo_16_vector.py's own docstring. pyproject.toml
would need `httpx` and `structlog` added before this module is guaranteed
to import cleanly elsewhere.

DEPENDENCY GAP NOTE (do not "fix" silently - report, as instructed):
    `httpx` and `structlog` are not listed in pyproject.toml's base
    dependencies or any of its extras (graph/qdrant/monitoring/persistence/
    llm/full). They happened to already be importable in this development
    environment, so this port and its smoke test actually ran - but that is
    incidental to this environment, not something this port installed.

The source's own pydantic-based app/models/schemas.py is NOT ported
verbatim - it defined ~25 API-request/response schemas for the stripped
FastAPI layer (BatchRequest, CIOConfig, PerformanceSnapshot, ServiceHealth,
etc.), most of which ConnectionPool/RequestBatcher never touch. Only the
small subset of types the real engine classes actually read/write
(PoolConfig, PoolStatus, PoolType, HealthStatus, Priority, RequestStatus,
HTTPRequest, HTTPResponse, RequestMetrics, OptimizedResponse) are ported
here, as plain dataclasses/str-Enums rather than pydantic BaseModels -
matching algo_15/16/19/20's own established convention of plain
dataclasses for ported support types, and consistent with "strip the
[web-framework validation] layer, keep the engine".

Real logic ported as-is (connection_pool.py):
    - Connection: real httpx.AsyncClient wrapping, real TTL
      (is_expired()) and idle-timeout (is_idle_timeout()) checks.
    - ConnectionPool: real asyncio.Semaphore-bounded pool with a real
      wait queue (acquire() tracks real wait times), real warmup to
      min_size, a real background _maintenance_loop() (runs every 10s)
      that evicts expired/idle connections and tops back up to min_size,
      and a real health-status calculation from tracked error/utilization
      rates (_update_health_status()).

Real logic ported as-is (request_batcher.py), INCLUDING the disclosed
2026-09-14 bug fix (kept fixed, not reintroduced):
    - RequestBatcher: real time-window batching (_collect_batch(), a
      real N-ms collection window with a 50ms max-wait override), real
      priority-aware bypass (CRITICAL requests skip batching entirely,
      same as backpressure overflow), and real adaptive parameter tuning
      (_adapt_parameters(): window/batch-size adjust based on tracked
      batch efficiency and processing time).
    - _process_single(): the source's own docstring documents that this
      previously ALWAYS called `item.future.set_result(None)` regardless
      of what the caller's real `processor` callable computed - i.e.
      every batched (non-CRITICAL, non-backpressure) request silently
      discarded its real result. That bug was already fixed in the
      Delentia-Private-OS source as of 2026-09-14 (item.processor is
      genuinely invoked and its real result/exception is what resolves
      the caller's future) - this port keeps that fix, it does not
      reintroduce the old `set_result(None)` placeholder. The smoke test
      below includes the same regression assertion the source's own test
      suite added for this fix (see
      Delentia-Private-OS/rct_platform/microservices/cio-optimizer/tests/
      test_cio.py::test_request_batcher_normal_priority_returns_real_processor_result).

Not ported: `app/core/cio_engine.py` (the FastAPI-facing orchestrator that
wires ConnectionPool + RequestBatcher + rate limiting + circuit breakers
together) - out of scope per this port's brief, which named only
connection_pool.py and request_batcher.py as the real logic to bring over.

Smoke-test methodology note: real outbound network calls are avoided in
favor of `unittest.mock.patch.object(httpx.AsyncClient, "request")`,
exactly the same technique the source repo's own pytest suite
(tests/test_cio.py) uses throughout - a real httpx.AsyncClient, real
Connection/ConnectionPool/RequestBatcher code paths (semaphore, reuse
tracking, TTL, batching, adaptive tuning), only the actual socket I/O
mocked at the class level, matching upstream precedent rather than
inventing a new testing approach here.

Usage::

    pool = ConnectionPool(PoolConfig(name="http", pool_type=PoolType.HTTP, min_size=1, max_size=4))
    await pool.start()
    async with pool.acquire() as conn:
        response = await conn.execute_request("GET", "https://example.com")
    await pool.stop()

    batcher = RequestBatcher(batch_window_ms=10, min_batch_size=2, max_batch_size=10)
    await batcher.start()
    result = await batcher.submit(HTTPRequest(url="https://example.com"), my_async_processor)
    await batcher.stop()
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Set

import httpx
import structlog

logger = structlog.get_logger()


# ============================================================================
# Support types (see module docstring for why these are plain
# dataclasses/enums rather than the source's pydantic BaseModels)
# ============================================================================

class PoolType(str, Enum):
    """Connection pool types"""
    HTTP = "http"
    DATABASE = "database"
    REDIS = "redis"
    CUSTOM = "custom"


class HealthStatus(str, Enum):
    """Health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class Priority(str, Enum):
    """Request priority levels (declaration order = processing order in RequestBatcher)"""
    CRITICAL = "critical"      # Process immediately (bypasses batching)
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class RequestStatus(str, Enum):
    """Request processing status"""
    PENDING = "pending"
    QUEUED = "queued"
    BATCHED = "batched"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class PoolConfig:
    """Connection pool configuration"""
    name: str
    pool_type: PoolType = PoolType.HTTP
    min_size: int = 10
    max_size: int = 100
    ttl_seconds: int = 300
    idle_timeout: int = 60
    connect_timeout: int = 5
    read_timeout: int = 30
    max_retries: int = 3
    backoff_factor: float = 0.5
    enable_keepalive: bool = True


@dataclass
class PoolStatus:
    """Connection pool status"""
    name: str
    pool_type: PoolType
    size: int
    active: int
    idle: int
    waiting: int
    health: HealthStatus
    created_connections: int = 0
    failed_connections: int = 0
    reuse_rate: float = 0.0
    avg_wait_time_ms: float = 0.0


@dataclass
class HTTPRequest:
    """Single HTTP request"""
    url: str
    method: str = "GET"
    id: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None
    params: Dict[str, str] = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    timeout: int = 30
    retry_count: int = 3


@dataclass
class HTTPResponse:
    """HTTP response data"""
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None
    encoding: Optional[str] = None


@dataclass
class RequestMetrics:
    """Metrics for a single request"""
    processing_time_ms: float = 0.0
    wait_time_ms: float = 0.0
    connection_time_ms: float = 0.0
    request_time_ms: float = 0.0
    response_time_ms: float = 0.0
    connection_reused: bool = False
    retry_attempts: int = 0
    batched: bool = False


@dataclass
class OptimizedResponse:
    """Response with optimization details"""
    request_id: str
    status: RequestStatus
    response: Optional[HTTPResponse] = None
    metrics: Optional[RequestMetrics] = None
    error: Optional[str] = None


# ============================================================================
# ConnectionPool - real async httpx connection pooling (connection_pool.py)
# ============================================================================

class Connection:
    """Represents a single connection in the pool"""

    def __init__(self, client: httpx.AsyncClient, pool_name: str):
        self.client = client
        self.pool_name = pool_name
        self.created_at = time.time()
        self.last_used_at = time.time()
        self.use_count = 0
        self.is_healthy = True
        self.is_in_use = False

    async def execute_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Execute HTTP request using this connection"""
        self.last_used_at = time.time()
        self.use_count += 1

        try:
            response = await self.client.request(method, url, **kwargs)
            return response
        except Exception:
            self.is_healthy = False
            raise

    def is_expired(self, ttl: int) -> bool:
        """Check if connection has exceeded TTL"""
        if ttl == 0:  # Infinite TTL
            return False
        age = time.time() - self.created_at
        return age > ttl

    def is_idle_timeout(self, timeout: int) -> bool:
        """Check if connection has been idle too long"""
        idle_time = time.time() - self.last_used_at
        return idle_time > timeout

    async def close(self):
        """Close the connection"""
        await self.client.aclose()


class ConnectionPool:
    """
    Async connection pool for HTTP requests

    Features:
    - Dynamic sizing (min/max)
    - Connection reuse
    - Health checking
    - TTL management
    - Idle timeout
    - Wait queue for connections
    """

    def __init__(self, config: PoolConfig):
        self.config = config
        self.name = config.name

        self._pool: Deque[Connection] = deque()
        self._in_use: Set[Connection] = set()
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(config.max_size)

        self._waiting: int = 0
        self._wait_times: Deque[float] = deque(maxlen=1000)

        self._created_count: int = 0
        self._failed_count: int = 0
        self._reused_count: int = 0
        self._total_requests: int = 0

        self._health_status = HealthStatus.HEALTHY
        self._last_health_check = datetime.utcnow()

        self._maintenance_task: Optional[asyncio.Task] = None
        self._started = False

        logger.info("connection_pool_created", pool_name=self.name, min_size=config.min_size, max_size=config.max_size)

    async def start(self):
        """Start the connection pool"""
        if self._started:
            return

        self._started = True

        await self._warmup()
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

        logger.info("connection_pool_started", pool_name=self.name)

    async def stop(self):
        """Stop the connection pool and close all connections"""
        if not self._started:
            return

        self._started = False

        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            all_connections = list(self._pool) + list(self._in_use)
            for conn in all_connections:
                await conn.close()

            self._pool.clear()
            self._in_use.clear()

        logger.info("connection_pool_stopped", pool_name=self.name)

    async def _warmup(self):
        """Pre-create minimum number of connections"""
        for _ in range(self.config.min_size):
            conn = await self._create_connection()
            if conn:
                self._pool.append(conn)

        logger.info("connection_pool_warmed_up", pool_name=self.name, connections=len(self._pool))

    async def _create_connection(self) -> Optional[Connection]:
        """Create a new connection"""
        try:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    timeout=30.0,
                    connect=self.config.connect_timeout,
                    read=self.config.read_timeout,
                    write=self.config.read_timeout,
                    pool=self.config.read_timeout,
                ),
                limits=httpx.Limits(
                    max_connections=1,
                    max_keepalive_connections=1 if self.config.enable_keepalive else 0,
                ),
            )

            conn = Connection(client, self.name)
            self._created_count += 1

            logger.debug("connection_created", pool_name=self.name, total_created=self._created_count)

            return conn

        except Exception as e:
            self._failed_count += 1
            logger.error("connection_creation_failed", pool_name=self.name, error=str(e), total_failed=self._failed_count)
            return None

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool

        Usage:
            async with pool.acquire() as conn:
                response = await conn.execute_request("GET", url)
        """
        start_wait = time.time()
        self._waiting += 1

        try:
            await self._semaphore.acquire()

            conn = await self._get_connection()

            if conn:
                self._reused_count += 1
            else:
                conn = await self._create_connection()
                if not conn:
                    raise RuntimeError(f"Failed to acquire connection from pool {self.name}")

            wait_time = time.time() - start_wait
            self._wait_times.append(wait_time)
            self._waiting -= 1

            async with self._lock:
                self._in_use.add(conn)
                conn.is_in_use = True

            self._total_requests += 1

            yield conn

        finally:
            async with self._lock:
                if conn in self._in_use:
                    self._in_use.remove(conn)
                    conn.is_in_use = False

                    if (conn.is_healthy and
                            not conn.is_expired(self.config.ttl_seconds) and
                            not conn.is_idle_timeout(self.config.idle_timeout)):
                        self._pool.append(conn)
                    else:
                        await conn.close()

            self._semaphore.release()

    async def _get_connection(self) -> Optional[Connection]:
        """Get an available connection from the pool"""
        async with self._lock:
            while self._pool:
                conn = self._pool.popleft()

                if (conn.is_healthy and not conn.is_expired(self.config.ttl_seconds)):
                    return conn
                else:
                    await conn.close()

            return None

    async def _maintenance_loop(self):
        """Background task for pool maintenance"""
        while self._started:
            try:
                await asyncio.sleep(10)  # Run every 10 seconds
                await self._perform_maintenance()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("maintenance_error", pool_name=self.name, error=str(e))

    async def _perform_maintenance(self):
        """Perform pool maintenance tasks"""
        async with self._lock:
            expired = []
            for conn in list(self._pool):
                if conn.is_expired(self.config.ttl_seconds) or conn.is_idle_timeout(self.config.idle_timeout):
                    expired.append(conn)
                    self._pool.remove(conn)

            for conn in expired:
                await conn.close()

            if expired:
                logger.info("expired_connections_removed", pool_name=self.name, count=len(expired))

            available = len(self._pool)
            if available < self.config.min_size:
                needed = self.config.min_size - available
                for _ in range(needed):
                    conn = await self._create_connection()
                    if conn:
                        self._pool.append(conn)

            self._update_health_status()

    def _update_health_status(self):
        """Update pool health status"""
        pool_size = len(self._pool) + len(self._in_use)
        utilization = len(self._in_use) / self.config.max_size if self.config.max_size > 0 else 0

        total_attempts = self._created_count
        error_rate = self._failed_count / total_attempts if total_attempts > 0 else 0

        if error_rate > 0.5 or pool_size < self.config.min_size // 2:
            self._health_status = HealthStatus.UNHEALTHY
        elif error_rate > 0.2 or utilization > 0.9:
            self._health_status = HealthStatus.DEGRADED
        else:
            self._health_status = HealthStatus.HEALTHY

        self._last_health_check = datetime.utcnow()

    def get_status(self) -> PoolStatus:
        """Get current pool status"""
        pool_size = len(self._pool) + len(self._in_use)
        reuse_rate = self._reused_count / self._total_requests if self._total_requests > 0 else 0
        avg_wait = sum(self._wait_times) / len(self._wait_times) if self._wait_times else 0

        return PoolStatus(
            name=self.name, pool_type=self.config.pool_type, size=pool_size,
            active=len(self._in_use), idle=len(self._pool), waiting=self._waiting,
            health=self._health_status, created_connections=self._created_count,
            failed_connections=self._failed_count, reuse_rate=reuse_rate,
            avg_wait_time_ms=avg_wait * 1000
        )

    async def resize(self, new_min: int, new_max: int):
        """Dynamically resize the pool"""
        async with self._lock:
            old_min = self.config.min_size
            old_max = self.config.max_size

            self.config.min_size = new_min
            self.config.max_size = new_max

            if new_max > old_max:
                for _ in range(new_max - old_max):
                    self._semaphore.release()
            elif new_max < old_max:
                for _ in range(old_max - new_max):
                    try:
                        self._semaphore._value -= 1
                    except Exception:
                        pass

        logger.info("pool_resized", pool_name=self.name, old_min=old_min, old_max=old_max, new_min=new_min, new_max=new_max)

    async def flush(self):
        """Flush all connections and recreate pool"""
        async with self._lock:
            for conn in list(self._pool):
                await conn.close()
            self._pool.clear()

            for conn in self._in_use:
                conn.is_healthy = False

        await self._warmup()

        logger.info("pool_flushed", pool_name=self.name)


# ============================================================================
# RequestBatcher - priority-aware request batching (request_batcher.py)
# ============================================================================

@dataclass
class BatchItem:
    """Single item in a batch"""
    request: HTTPRequest
    future: "asyncio.Future"
    priority: Priority
    queued_at: float
    processor: Optional[Callable] = None
    batch_id: Optional[str] = None


class RequestBatcher:
    """
    Intelligent request batcher

    Features:
    - Time-based batching (collect for N ms)
    - Size-based batching (collect N requests)
    - Priority-aware (critical requests bypass batching)
    - Adaptive thresholds (adjust based on performance)
    - Backpressure handling
    """

    def __init__(
        self, batch_window_ms: int = 10, min_batch_size: int = 2,
        max_batch_size: int = 50, max_queue_depth: int = 1000, adaptive: bool = True,
    ):
        self.batch_window_ms = batch_window_ms
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.max_queue_depth = max_queue_depth
        self.adaptive = adaptive

        self._queues: Dict[Priority, Deque[BatchItem]] = {priority: deque() for priority in Priority}
        self._queue_lock = asyncio.Lock()

        self._processor_task: Optional[asyncio.Task] = None
        self._started = False

        self._batches_processed = 0
        self._requests_batched = 0
        self._requests_bypassed = 0
        self._batch_sizes: Deque[int] = deque(maxlen=100)
        self._batch_times: Deque[float] = deque(maxlen=100)

        self._current_batch_size = max_batch_size
        self._current_window_ms = batch_window_ms
        self._target_efficiency = 0.7  # 70% full minimum

        logger.info("request_batcher_created", window_ms=batch_window_ms, min_size=min_batch_size, max_size=max_batch_size)

    async def start(self):
        """Start the batcher"""
        if self._started:
            return

        self._started = True
        self._processor_task = asyncio.create_task(self._batch_processor())

        logger.info("request_batcher_started")

    async def stop(self):
        """Stop the batcher"""
        if not self._started:
            return

        self._started = False

        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        async with self._queue_lock:
            for queue in self._queues.values():
                for item in queue:
                    if not item.future.done():
                        item.future.cancel()
                queue.clear()

        logger.info("request_batcher_stopped")

    async def submit(self, request: HTTPRequest, processor: Callable) -> Any:
        """
        Submit request for batching

        Args:
            request: HTTP request to process
            processor: Async function to process the request

        Returns:
            Whatever `processor` returns for this request.
        """
        priority = request.priority

        if priority == Priority.CRITICAL:
            self._requests_bypassed += 1
            return await processor(request)

        total_queued = sum(len(q) for q in self._queues.values())
        if total_queued >= self.max_queue_depth:
            logger.warning("queue_full", total_queued=total_queued, max_depth=self.max_queue_depth)
            self._requests_bypassed += 1
            return await processor(request)

        future = asyncio.get_event_loop().create_future()
        item = BatchItem(request=request, future=future, priority=priority, queued_at=time.time(), processor=processor)

        async with self._queue_lock:
            self._queues[priority].append(item)

        return await future

    async def _batch_processor(self):
        """Background task to process batches"""
        while self._started:
            try:
                await asyncio.sleep(self._current_window_ms / 1000.0)

                batch = await self._collect_batch()

                if not batch:
                    continue

                await self._process_batch(batch)

                if self.adaptive:
                    self._adapt_parameters()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("batch_processor_error", error=str(e))

    async def _collect_batch(self) -> List[BatchItem]:
        """Collect a batch of requests from queues"""
        batch: List[BatchItem] = []

        async with self._queue_lock:
            for priority in Priority:
                queue = self._queues[priority]

                while queue and len(batch) < self._current_batch_size:
                    batch.append(queue.popleft())

                if len(batch) >= self.min_batch_size:
                    break

        if batch:
            max_wait = max(time.time() - item.queued_at for item in batch)
            if len(batch) >= self.min_batch_size or max_wait > 0.050:  # 50ms max wait
                return batch
            else:
                async with self._queue_lock:
                    for item in reversed(batch):
                        self._queues[item.priority].appendleft(item)
                return []

        return []

    async def _process_batch(self, batch: List[BatchItem]):
        """Process a batch of requests"""
        if not batch:
            return

        batch_id = f"batch_{int(time.time() * 1000)}"
        start_time = time.time()

        logger.info("processing_batch", batch_id=batch_id, size=len(batch), priorities=[item.priority.value for item in batch])

        grouped = defaultdict(list)
        for item in batch:
            url = item.request.url
            grouped[url].append(item)

        tasks = []
        for url, items in grouped.items():
            task = asyncio.create_task(self._process_group(batch_id, items))
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

        batch_time = time.time() - start_time
        self._batches_processed += 1
        self._requests_batched += len(batch)
        self._batch_sizes.append(len(batch))
        self._batch_times.append(batch_time)

        logger.info("batch_processed", batch_id=batch_id, size=len(batch), time_ms=batch_time * 1000, groups=len(grouped))

    async def _process_group(self, batch_id: str, items: List[BatchItem]):
        """Process a group of requests to the same target"""
        tasks = []
        for item in items:
            item.batch_id = batch_id
            task = asyncio.create_task(self._process_single(item))
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_single(self, item: BatchItem):
        """
        Process a single request in the batch.

        Fixed 2026-09-14 in the source (kept fixed here, see module
        docstring): genuinely invokes the stored processor and resolves
        the caller's future with its real result/exception, instead of
        always resolving to None.
        """
        try:
            if not item.future.done():
                if item.processor is not None:
                    result = await item.processor(item.request)
                else:
                    result = None
                item.future.set_result(result)
        except Exception as e:
            if not item.future.done():
                item.future.set_exception(e)

    def _adapt_parameters(self):
        """Adapt batching parameters based on performance"""
        if not self._batch_sizes:
            return

        avg_size = sum(self._batch_sizes) / len(self._batch_sizes)
        efficiency = avg_size / self.max_batch_size

        avg_time = sum(self._batch_times) / len(self._batch_times) if self._batch_times else 0
        target_time = self._current_window_ms / 1000.0

        if efficiency < self._target_efficiency:
            self._current_window_ms = min(self._current_window_ms + 2, self.batch_window_ms * 2)
        elif efficiency > 0.95:
            self._current_window_ms = max(self._current_window_ms - 1, self.batch_window_ms // 2)

        if avg_time > target_time * 1.5:
            self._current_batch_size = max(self.min_batch_size, int(self._current_batch_size * 0.8))
        elif avg_time < target_time * 0.5:
            self._current_batch_size = min(self.max_batch_size, int(self._current_batch_size * 1.2))

        logger.debug("batch_parameters_adapted", window_ms=self._current_window_ms, batch_size=self._current_batch_size,
                      efficiency=efficiency, avg_time_ms=avg_time * 1000)

    def get_stats(self) -> Dict:
        """Get batcher statistics"""
        total_requests = self._requests_batched + self._requests_bypassed
        batch_ratio = self._requests_batched / total_requests if total_requests > 0 else 0

        avg_batch_size = sum(self._batch_sizes) / len(self._batch_sizes) if self._batch_sizes else 0
        avg_batch_time = sum(self._batch_times) / len(self._batch_times) if self._batch_times else 0

        efficiency = avg_batch_size / self.max_batch_size if self.max_batch_size > 0 else 0

        return {
            "batches_processed": self._batches_processed, "requests_batched": self._requests_batched,
            "requests_bypassed": self._requests_bypassed, "total_requests": total_requests,
            "batch_ratio": batch_ratio, "avg_batch_size": avg_batch_size,
            "avg_batch_time_ms": avg_batch_time * 1000, "batch_efficiency": efficiency,
            "current_window_ms": self._current_window_ms, "current_batch_size": self._current_batch_size,
            "queued": {priority.value: len(queue) for priority, queue in self._queues.items()}
        }


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    import asyncio as _asyncio
    from unittest.mock import Mock, patch

    async def _smoke_test():
        print("=== ALGO-28 CIO Optimizer smoke test ===")

        # --- ConnectionPool: real asyncio.Semaphore pooling, warmup, reuse, TTL/idle eviction ---
        # Mocked at the httpx.AsyncClient.request level, same technique the
        # source repo's own test suite uses (tests/test_cio.py) - see module
        # docstring's "Smoke-test methodology note". Everything else
        # (Connection/ConnectionPool bookkeeping, real asyncio.Semaphore,
        # real TTL/idle-timeout math) is genuinely exercised.
        with patch.object(httpx.AsyncClient, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.json.return_value = {"ok": True}

            async def _fake_request(*args, **kwargs):
                return mock_response
            mock_request.side_effect = _fake_request

            config = PoolConfig(
                name="smoke_pool", pool_type=PoolType.HTTP,
                min_size=2, max_size=4, ttl_seconds=100, idle_timeout=100,
                connect_timeout=5, read_timeout=10,
            )
            pool = ConnectionPool(config)
            await pool.start()

            status = pool.get_status()
            print(f"Pool status after start() (real warmup to min_size): {status}")
            assert status.size >= config.min_size
            assert status.idle >= config.min_size
            assert status.health == HealthStatus.HEALTHY

            # Acquire + release: real semaphore + real reuse path
            async with pool.acquire() as conn:
                assert conn.is_in_use is True
                response = await conn.execute_request("GET", "https://example.invalid/get")
                assert response.status_code == 200

            status_after = pool.get_status()
            print(f"Pool status after one acquire/release: {status_after}")
            assert status_after.idle >= 1, "connection must have been returned to the pool, not leaked"

            # Concurrent acquisition bounded by the real semaphore (max_size=4)
            async def _hold_and_release():
                async with pool.acquire() as c:
                    await _asyncio.sleep(0.01)
                    return c.use_count

            results = await _asyncio.gather(*[_hold_and_release() for _ in range(8)])
            print(f"8 concurrent acquires against max_size=4 all completed: use_counts={results}")
            assert len(results) == 8

            final_status = pool.get_status()
            print(f"Final pool status: {final_status}")
            assert final_status.created_connections >= config.min_size
            assert final_status.reuse_rate > 0, "at least some real connection reuse must have happened"

            # Real TTL eviction: force one pooled connection to look expired, then run real maintenance.
            # With idle pool size (4) staying >= min_size (2) after evicting just one, the real
            # _perform_maintenance() correctly does NOT top back up - so we assert the eviction
            # itself happened (idle count dropped), not a replacement that isn't owed here.
            assert len(pool._pool) > 0
            pool._pool[0].created_at = time.time() - (config.ttl_seconds + 10)
            idle_before = len(pool._pool)
            await pool._perform_maintenance()
            idle_after = len(pool._pool)
            print(f"After forcing TTL expiry + real _perform_maintenance(): "
                  f"idle before={idle_before}, idle after={idle_after} (min_size={config.min_size})")
            assert idle_after == idle_before - 1, "the real expiry check must have evicted exactly the one forced-expired connection"

            # Now force enough expiries that the idle pool drops BELOW min_size, proving
            # _perform_maintenance() really does top back up to min_size in that case.
            for conn in list(pool._pool):
                conn.created_at = time.time() - (config.ttl_seconds + 10)
            created_before_topup = pool.get_status().created_connections
            await pool._perform_maintenance()
            status_after_topup = pool.get_status()
            print(f"After expiring ALL idle connections + real _perform_maintenance(): {status_after_topup}, "
                  f"created_connections {created_before_topup} -> {status_after_topup.created_connections}")
            assert status_after_topup.idle >= config.min_size, "must have topped back up to min_size"
            assert status_after_topup.created_connections > created_before_topup, \
                "topping back up to min_size must have really created new connections"

            await pool.stop()
            assert len(pool._pool) == 0 and len(pool._in_use) == 0
            print("Pool stopped, all connections closed.")

        # --- RequestBatcher: real batching + the preserved 2026-09-14 bug fix ---
        batcher = RequestBatcher(batch_window_ms=15, min_batch_size=2, max_batch_size=10)
        await batcher.start()

        # CRITICAL bypasses batching entirely
        async def echo_processor(req: HTTPRequest):
            return {"echo": req.url, "priority": req.priority.value}

        critical_result = await batcher.submit(
            HTTPRequest(url="https://example.invalid/critical", priority=Priority.CRITICAL), echo_processor
        )
        print(f"CRITICAL request bypass result: {critical_result}")
        assert critical_result == {"echo": "https://example.invalid/critical", "priority": "critical"}
        assert batcher._requests_bypassed == 1

        # Regression check for the 2026-09-14 fix: NORMAL-priority requests must get their
        # REAL processor result back, not a silently-discarded None (the old bug).
        call_count = {"n": 0}

        async def real_processor(req: HTTPRequest):
            call_count["n"] += 1
            return {"processed": True, "url": req.url, "call_number": call_count["n"]}

        normal_result = await batcher.submit(
            HTTPRequest(url="https://example.invalid/normal-item", priority=Priority.NORMAL), real_processor
        )
        print(f"NORMAL-priority (batched) request result: {normal_result}")
        assert normal_result is not None, "regression: the real processor's result must not be silently discarded as None"
        assert normal_result["processed"] is True and normal_result["url"] == "https://example.invalid/normal-item"
        assert call_count["n"] == 1, "the processor must actually have been invoked exactly once"

        # Two different NORMAL requests batched together must each get their OWN real result
        async def echo_url_processor(req: HTTPRequest):
            return {"echo": req.url}

        result_a, result_b = await _asyncio.gather(
            batcher.submit(HTTPRequest(url="https://example.invalid/a", priority=Priority.NORMAL), echo_url_processor),
            batcher.submit(HTTPRequest(url="https://example.invalid/b", priority=Priority.NORMAL), echo_url_processor),
        )
        print(f"Two concurrently-batched requests -> a={result_a}, b={result_b}")
        assert result_a == {"echo": "https://example.invalid/a"}
        assert result_b == {"echo": "https://example.invalid/b"}
        assert result_a != result_b, "regression: distinct batched requests must not collapse to the same result"

        # The futures resolve inside _process_single (a sibling Task) slightly before
        # _process_batch's own stats increment (right after its enclosing gather)
        # actually runs on the event loop - give it one tick to settle before reading stats.
        await _asyncio.sleep(0.02)
        stats = batcher.get_stats()
        print(f"RequestBatcher stats: {stats}")
        assert stats["requests_batched"] >= 3
        assert stats["requests_bypassed"] == 1
        assert "batch_efficiency" in stats

        await batcher.stop()
        print("Batcher stopped.")

        print("=== ALGO-28 CIO Optimizer: ALL ASSERTIONS PASSED ===")

    _asyncio.run(_smoke_test())
