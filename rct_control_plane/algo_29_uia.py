"""
ALGO-29: UIA — Universal Integrations Adapter

Ported from Delentia-Private-OS's real universal-adapter layer at
rct_platform/microservices/uia-integrations/app/adapters/universal_adapters.py
(classes RESTAdapter, GraphQLAdapter, WebSocketAdapter, DatabaseAdapter,
MessageQueueAdapter, AdapterFactory) together with the abstract
BaseAdapter from app/core/plugin_system.py and the minimal enum/config
types from app/models/schemas.py that those classes actually depend on.

The private-repo source itself already documents (inline, dated
2026-09-14) that this module was audited and had its adapters wired to
real client libraries where a real one is available:

- RESTAdapter: real httpx.AsyncClient calls (auth headers, retries with
  backoff on 429/500/502/503/504, real HTTP methods). Unchanged.
- GraphQLAdapter: real gql/AIOHTTPTransport calls against a real GraphQL
  endpoint. Unchanged.
- WebSocketAdapter: real `websockets` connections (send/receive/connect/
  close) — the source notes this previously always returned a hardcoded
  mock result without ever touching a socket; that was already fixed in
  the source and is kept as-is here.
- DatabaseAdapter: real `asyncpg` PostgreSQL connection pool when asyncpg
  is installed AND a real database is reachable; otherwise an HONEST
  fallback with `"simulated": True` in the result — never a fabricated
  "it worked". This port keeps that honest fallback exactly as-is (per
  this port's brief) rather than forcing a live DB requirement. asyncpg
  is NOT installed in this Delentia-OS environment (verified), so
  DatabaseAdapter will exercise the simulated path here — which is the
  correct, disclosed behavior, not a bug.
- MessageQueueAdapter: NO real broker client (aio-pika/aiokafka/etc.) is
  a dependency anywhere in this environment or the source's own
  requirements.txt, so every result is honestly marked "simulated": True.
  Kept as disclosed simulation per this port's brief — not "fixed" into a
  fake real connection.

Only change from the source: the abstract BaseAdapter class and the
AdapterType/AuthType/AuthConfig types it and the adapters depend on are
inlined below (as a plain dataclass + two str-Enums) instead of importing
`app.core.plugin_system` / `app.models.schemas`, since this port only
needs the adapter layer, not the full plugin-loading/pydantic-schema
machinery those private-repo modules also contain. No adapter logic
itself was changed to make this work — AuthConfig keeps the exact same
attributes (`type`, `api_key`, `token`, `username`, `password`,
`custom_headers`) the adapters already read via `self.auth_config.X`.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

logger = logging.getLogger(__name__)


# ============================================================================
# Minimal types (inlined from app/models/schemas.py — only what the
# adapters below actually reference)
# ============================================================================

class AdapterType(str, Enum):
    """Integration adapter types"""
    REST = "REST"
    GRAPHQL = "GraphQL"
    GRPC = "gRPC"
    WEBSOCKET = "WebSocket"
    DATABASE = "Database"
    MESSAGE_QUEUE = "MessageQueue"
    CUSTOM = "Custom"


class AuthType(str, Enum):
    """Authentication types"""
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    JWT = "jwt"
    CUSTOM = "custom"


@dataclass
class AuthConfig:
    """Authentication configuration (plain dataclass port of the source's
    pydantic AuthConfig — same field names, adapters read them unchanged)."""
    type: AuthType = AuthType.NONE
    api_key: Optional[str] = None
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    oauth2_client_id: Optional[str] = None
    oauth2_client_secret: Optional[str] = None
    oauth2_token_url: Optional[str] = None
    custom_headers: Optional[Dict[str, str]] = None


# ============================================================================
# BASE ADAPTER CLASS (straight port of app/core/plugin_system.BaseAdapter)
# ============================================================================

class BaseAdapter(abc.ABC):
    """Abstract base class for all integration adapters."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.adapter_type = self.get_adapter_type()
        self._call_count = 0
        self._success_count = 0
        self._error_count = 0
        self._total_overhead_ms = 0.0

    @abc.abstractmethod
    def get_adapter_type(self) -> AdapterType:
        pass

    @abc.abstractmethod
    async def execute_request(self, action: str, parameters: Dict[str, Any], timeout: int = 30) -> Any:
        pass

    @abc.abstractmethod
    async def test_connection(self) -> bool:
        pass

    async def close(self) -> None:
        pass

    def record_call(self, success: bool, overhead_ms: float) -> None:
        self._call_count += 1
        if success:
            self._success_count += 1
        else:
            self._error_count += 1
        self._total_overhead_ms += overhead_ms

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "total_calls": self._call_count,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "success_rate": (
                (self._success_count / self._call_count * 100)
                if self._call_count > 0 else 0.0
            ),
            "avg_overhead_ms": (
                self._total_overhead_ms / self._call_count
                if self._call_count > 0 else 0.0
            ),
        }


# ============================================================================
# REST ADAPTER (unmodified logic)
# ============================================================================

class RESTAdapter(BaseAdapter):
    """Universal REST API adapter with multiple auth methods"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("base_url", "")
        self.auth_config: AuthConfig = config.get("auth") or AuthConfig()
        self.default_headers = config.get("headers", {})
        self.timeout = config.get("timeout", 30)
        self.retry_attempts = config.get("retry_attempts", 3)
        self.retry_backoff = config.get("retry_backoff", 1.0)

        self._client: Optional[httpx.AsyncClient] = None

    def get_adapter_type(self) -> AdapterType:
        return AdapterType.REST

    def _get_auth_headers(self) -> Dict[str, str]:
        headers = self.default_headers.copy()

        if self.auth_config.type == AuthType.BEARER:
            headers["Authorization"] = f"Bearer {self.auth_config.token}"
        elif self.auth_config.type == AuthType.API_KEY:
            headers["Authorization"] = f"ApiKey {self.auth_config.api_key}"
        elif self.auth_config.type == AuthType.BASIC:
            pass
        elif self.auth_config.type == AuthType.CUSTOM and self.auth_config.custom_headers:
            headers.update(self.auth_config.custom_headers)

        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            auth = None
            if self.auth_config.type == AuthType.BASIC:
                auth = httpx.BasicAuth(
                    username=self.auth_config.username,
                    password=self.auth_config.password
                )

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._get_auth_headers(),
                auth=auth,
                timeout=httpx.Timeout(
                    timeout=self.timeout,
                    connect=10.0,
                    read=self.timeout,
                    write=self.timeout,
                    pool=5.0
                ),
                follow_redirects=True,
            )

        return self._client

    async def execute_request(self, action: str, parameters: Dict[str, Any], timeout: int = 30) -> Any:
        parts = action.split(" ", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid action format: {action}. Expected 'METHOD /path'")

        method, path = parts
        method = method.upper()

        query_params = parameters.get("query", {})
        body = parameters.get("body")
        extra_headers = parameters.get("headers", {})

        client = await self._get_client()

        last_exception = None
        start_time = time.time()

        for attempt in range(self.retry_attempts):
            try:
                response = await client.request(
                    method=method,
                    url=path,
                    params=query_params,
                    json=body if body else None,
                    headers=extra_headers,
                    timeout=timeout,
                )
                response.raise_for_status()

                overhead_ms = (time.time() - start_time) * 1000
                self.record_call(success=True, overhead_ms=overhead_ms)

                try:
                    return response.json()
                except Exception:
                    return response.text

            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code in [429, 500, 502, 503, 504]:
                    if attempt < self.retry_attempts - 1:
                        await asyncio.sleep(self.retry_backoff ** attempt)
                        continue
                break

            except httpx.RequestError as e:
                last_exception = e
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_backoff ** attempt)
                    continue
                break

        overhead_ms = (time.time() - start_time) * 1000
        self.record_call(success=False, overhead_ms=overhead_ms)
        if last_exception is not None:
            raise last_exception
        raise RuntimeError(f"UIA adapter call failed with no retry attempts executed (retry_attempts={self.retry_attempts})")

    async def test_connection(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.head("/", timeout=5.0)
            return response.status_code < 500
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ============================================================================
# GRAPHQL ADAPTER (unmodified logic)
# ============================================================================

class GraphQLAdapter(BaseAdapter):
    """Universal GraphQL adapter"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.endpoint = config.get("endpoint", "")
        self.auth_config: AuthConfig = config.get("auth") or AuthConfig()
        self.default_headers = config.get("headers", {})
        self.timeout = config.get("timeout", 30)

        self._client: Optional[Client] = None
        self._transport: Optional[AIOHTTPTransport] = None

    def get_adapter_type(self) -> AdapterType:
        return AdapterType.GRAPHQL

    def _get_auth_headers(self) -> Dict[str, str]:
        headers = self.default_headers.copy()

        if self.auth_config.type == AuthType.BEARER:
            headers["Authorization"] = f"Bearer {self.auth_config.token}"
        elif self.auth_config.type == AuthType.API_KEY:
            headers["Authorization"] = f"ApiKey {self.auth_config.api_key}"
        elif self.auth_config.type == AuthType.CUSTOM and self.auth_config.custom_headers:
            headers.update(self.auth_config.custom_headers)

        return headers

    async def _get_client(self) -> Client:
        if self._client is None:
            self._transport = AIOHTTPTransport(
                url=self.endpoint,
                headers=self._get_auth_headers(),
                timeout=self.timeout
            )
            self._client = Client(
                transport=self._transport,
                fetch_schema_from_transport=False
            )

        return self._client

    async def execute_request(self, action: str, parameters: Dict[str, Any], timeout: int = 30) -> Any:
        if "query" not in parameters:
            raise ValueError("GraphQL query must be provided in parameters['query']")

        query_string = parameters["query"]
        variables = parameters.get("variables", {})

        client = await self._get_client()
        start_time = time.time()

        try:
            query_doc = gql(query_string)

            async with client as session:
                result = await session.execute(query_doc, variable_values=variables)

            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=True, overhead_ms=overhead_ms)

            return result

        except Exception:
            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=False, overhead_ms=overhead_ms)
            raise

    async def test_connection(self) -> bool:
        try:
            result = await self.execute_request(
                action="query",
                parameters={"query": "{ __schema { queryType { name } } }"},
                timeout=5
            )
            return result is not None
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.close_async()
            self._client = None
        if self._transport:
            await self._transport.close()
            self._transport = None


# ============================================================================
# WEBSOCKET ADAPTER (unmodified logic — real `websockets` connections)
# ============================================================================

class WebSocketAdapter(BaseAdapter):
    """Universal WebSocket adapter"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("url", "")
        self.auth_config: AuthConfig = config.get("auth") or AuthConfig()
        self.protocols = config.get("protocols", [])
        self.timeout = config.get("timeout", 30)

        self._connection = None

    def get_adapter_type(self) -> AdapterType:
        return AdapterType.WEBSOCKET

    async def _ensure_connected(self) -> None:
        if self._connection is not None:
            return
        import websockets
        self._connection = await asyncio.wait_for(
            websockets.connect(self.url, subprotocols=self.protocols or None),
            timeout=self.timeout,
        )

    async def execute_request(self, action: str, parameters: Dict[str, Any], timeout: int = 30) -> Any:
        start_time = time.time()

        try:
            if action == "send":
                message = parameters.get("message")
                if not message:
                    raise ValueError("Message required for send action")

                await self._ensure_connected()
                await asyncio.wait_for(self._connection.send(message), timeout=timeout)
                result = {"status": "sent", "message": message}

            elif action == "receive":
                await self._ensure_connected()
                received = await asyncio.wait_for(self._connection.recv(), timeout=timeout)
                result = {"status": "received", "message": received}

            elif action == "connect":
                await self._ensure_connected()
                result = {"status": "connected", "url": self.url}

            elif action == "close":
                await self.close()
                result = {"status": "closed"}

            else:
                raise ValueError(f"Unknown WebSocket action: {action}")

            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=True, overhead_ms=overhead_ms)

            return result

        except Exception:
            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=False, overhead_ms=overhead_ms)
            raise

    async def test_connection(self) -> bool:
        try:
            await self._ensure_connected()
            await self.close()
            return True
        except Exception as e:
            logger.warning(f"WebSocket connection test failed for {self.url}: {e}")
            return False

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None


# ============================================================================
# DATABASE ADAPTER (unmodified logic — real asyncpg with honest fallback)
# ============================================================================

class DatabaseAdapter(BaseAdapter):
    """Universal Database adapter (SQL and NoSQL)"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 5432)
        self.database = config.get("database", "")
        self.user = config.get("user", "")
        self.password = config.get("password", "")
        self.pool_min_size = config.get("pool_min_size", 5)
        self.pool_max_size = config.get("pool_max_size", 20)
        self.timeout = config.get("timeout", 30)

        self._pool = None

    def get_adapter_type(self) -> AdapterType:
        return AdapterType.DATABASE

    async def _get_pool(self):
        """Lazily create a real asyncpg pool; returns None (never raises) if
        asyncpg isn't installed or the database isn't reachable."""
        if self._pool is not None:
            return self._pool
        try:
            import asyncpg
        except ImportError:
            logger.warning("asyncpg not installed - DatabaseAdapter cannot connect for real, falling back to simulation")
            return None
        try:
            self._pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    min_size=self.pool_min_size,
                    max_size=self.pool_max_size,
                ),
                timeout=self.timeout,
            )
            return self._pool
        except Exception as e:
            logger.warning(f"Real database connection failed for {self.host}:{self.port}/{self.database}: {e}")
            return None

    async def execute_request(self, action: str, parameters: Dict[str, Any], timeout: int = 30) -> Any:
        if "query" not in parameters:
            raise ValueError("Database query must be provided in parameters['query']")

        query = parameters["query"]
        params = parameters.get("params", [])

        start_time = time.time()

        try:
            pool = await self._get_pool()

            if pool is not None:
                async with pool.acquire() as conn:
                    if action == "fetch_one":
                        row = await asyncio.wait_for(conn.fetchrow(query, *params), timeout=timeout)
                        rows = [dict(row)] if row else []
                    elif action == "fetch_many":
                        records = await asyncio.wait_for(conn.fetch(query, *params), timeout=timeout)
                        rows = [dict(r) for r in records]
                    else:  # "query" / "execute"
                        status = await asyncio.wait_for(conn.execute(query, *params), timeout=timeout)
                        rows = []
                        parts = status.split()
                        row_count = int(parts[-1]) if parts and parts[-1].isdigit() else 0
                        result = {"query": query, "params": params, "rows_affected": row_count, "result": rows, "simulated": False}
                        overhead_ms = (time.time() - start_time) * 1000
                        self.record_call(success=True, overhead_ms=overhead_ms)
                        return result

                    result = {"query": query, "params": params, "rows_affected": len(rows), "result": rows, "simulated": False}
                    overhead_ms = (time.time() - start_time) * 1000
                    self.record_call(success=True, overhead_ms=overhead_ms)
                    return result

            # No real connection available - disclosed simulation.
            result = {
                "query": query,
                "params": params,
                "rows_affected": 1,
                "result": [],
                "simulated": True,
            }

            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=True, overhead_ms=overhead_ms)

            return result

        except Exception:
            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=False, overhead_ms=overhead_ms)
            raise

    async def test_connection(self) -> bool:
        pool = await self._get_pool()
        return pool is not None

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


# ============================================================================
# MESSAGE QUEUE ADAPTER (unmodified logic — honestly disclosed simulation)
# ============================================================================

class MessageQueueAdapter(BaseAdapter):
    """Universal Message Queue adapter (RabbitMQ, Kafka, etc.) — no real
    broker client dependency exists anywhere in this environment, so every
    result is honestly marked "simulated": True rather than left ambiguous."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.broker_url = config.get("broker_url", "")
        self.queue_name = config.get("queue_name", "")
        self.topic = config.get("topic", "")
        self.timeout = config.get("timeout", 30)

        self._connection = None

    def get_adapter_type(self) -> AdapterType:
        return AdapterType.MESSAGE_QUEUE

    async def execute_request(self, action: str, parameters: Dict[str, Any], timeout: int = 30) -> Any:
        start_time = time.time()

        try:
            if action == "publish":
                _message = parameters.get("message")
                result = {"status": "published", "message_id": "mock_id", "simulated": True}

            elif action == "consume":
                result = {"status": "consumed", "message": "mock_message", "simulated": True}

            elif action == "ack":
                result = {"status": "acknowledged", "simulated": True}

            elif action == "nack":
                result = {"status": "nacked", "simulated": True}

            else:
                raise ValueError(f"Unknown message queue action: {action}")

            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=True, overhead_ms=overhead_ms)

            return result

        except Exception:
            overhead_ms = (time.time() - start_time) * 1000
            self.record_call(success=False, overhead_ms=overhead_ms)
            raise

    async def test_connection(self) -> bool:
        return False

    async def close(self) -> None:
        if self._connection:
            self._connection = None


# ============================================================================
# ADAPTER FACTORY (unmodified logic)
# ============================================================================

class AdapterFactory:
    """Factory for creating adapters"""

    @staticmethod
    def create_adapter(adapter_type: AdapterType, config: Dict[str, Any]) -> BaseAdapter:
        if adapter_type == AdapterType.REST:
            return RESTAdapter(config)
        elif adapter_type == AdapterType.GRAPHQL:
            return GraphQLAdapter(config)
        elif adapter_type == AdapterType.WEBSOCKET:
            return WebSocketAdapter(config)
        elif adapter_type == AdapterType.DATABASE:
            return DatabaseAdapter(config)
        elif adapter_type == AdapterType.MESSAGE_QUEUE:
            return MessageQueueAdapter(config)
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")


if __name__ == "__main__":
    import asyncio as _asyncio

    async def _main():
        print("=" * 70)
        print("ALGO-29 UIA — smoke test (real REST/GraphQL/WebSocket calls)")
        print("=" * 70)

        # --- REST: real call to the local Ollama server's REST API ---
        rest = AdapterFactory.create_adapter(
            AdapterType.REST,
            {"base_url": "http://127.0.0.1:11434", "auth": AuthConfig(type=AuthType.NONE)},
        )
        rest_result = await rest.execute_request("GET /api/tags", {})
        print(f"\n[REST] GET /api/tags -> {len(rest_result.get('models', []))} local Ollama models")
        assert isinstance(rest_result, dict) and "models" in rest_result
        await rest.close()

        # --- GraphQL: real call to a public GraphQL API (countries.trevorblades.com) ---
        gql_adapter = AdapterFactory.create_adapter(
            AdapterType.GRAPHQL,
            {"endpoint": "https://countries.trevorblades.com/", "auth": AuthConfig(type=AuthType.NONE)},
        )
        gql_result = await gql_adapter.execute_request(
            "query",
            {"query": '{ country(code: "US") { name capital } }'},
        )
        print(f"[GraphQL] country(US) -> {gql_result}")
        assert gql_result["country"]["name"] == "United States"
        await gql_adapter.close()

        # --- WebSocket: real connection + real echo round-trip ---
        ws = AdapterFactory.create_adapter(
            AdapterType.WEBSOCKET,
            {"url": "wss://echo.websocket.org"},
        )
        connect_result = await ws.execute_request("connect", {})
        print(f"[WebSocket] connect -> {connect_result}")
        # echo.websocket.org sends a connection banner as the first frame
        banner = await ws.execute_request("receive", {})
        print(f"[WebSocket] banner  -> {banner}")
        send_result = await ws.execute_request("send", {"message": "hello from ALGO-29 smoke test"})
        print(f"[WebSocket] send    -> {send_result}")
        recv_result = await ws.execute_request("receive", {})
        print(f"[WebSocket] receive -> {recv_result}")
        assert recv_result["message"] == "hello from ALGO-29 smoke test"
        await ws.close()

        # --- Database: no asyncpg installed in this environment -> honest simulation ---
        db = AdapterFactory.create_adapter(
            AdapterType.DATABASE,
            {"host": "localhost", "port": 5432, "database": "nope", "user": "nope", "password": "nope"},
        )
        db_connected = await db.test_connection()
        db_result = await db.execute_request("query", {"query": "SELECT 1"})
        print(f"[Database] test_connection -> {db_connected} (expected False: asyncpg not installed)")
        print(f"[Database] execute_request -> {db_result}")
        assert db_connected is False
        assert db_result["simulated"] is True

        # --- MessageQueue: honestly disclosed simulation (no broker client dependency) ---
        mq = AdapterFactory.create_adapter(AdapterType.MESSAGE_QUEUE, {"broker_url": "amqp://nope"})
        mq_connected = await mq.test_connection()
        mq_result = await mq.execute_request("publish", {"message": "x"})
        print(f"[MessageQueue] test_connection -> {mq_connected} (expected False, honestly disclosed)")
        print(f"[MessageQueue] publish -> {mq_result}")
        assert mq_connected is False
        assert mq_result["simulated"] is True

        print("\nALL ASSERTIONS PASSED")

    _asyncio.run(_main())
