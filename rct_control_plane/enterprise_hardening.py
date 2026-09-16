"""
Layer 10: Enterprise Hardening — real JWT RS256 + Circuit Breaker
(2026-09-16).

Two capabilities the master architecture doc explicitly names for Layer
10 ("ออกใบรับรอง JWT (RS256 Signature)" and "วงจร Circuit Breaker ป้องกัน
ระบบล่มต่อเนื่อง") that did not exist anywhere in this engagement until
now — this workspace's `full` extra already depended on real crypto
libraries (`cryptography`, and `PyJWT` is available in this environment)
for exactly this kind of thing, but nothing used them for JWT issuing.

Rate limiting and the Cloudflare/Zuplo edge delivery half of Layer 10
are NOT part of this file — those already exist, partially, on the
TypeScript side (delentia-mcp-ecosystem) per this engagement's own
earlier gap reports, and are out of scope for a Python module.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption, load_pem_private_key,
)


# ============================================================================
# Real JWT RS256 issuing/verification
# ============================================================================

class RS256KeyPair:
    """Real RSA keypair for RS256-signed JWTs (asymmetric — the private
    key signs, a distinct public key verifies, matching the doc's
    "JWT (RS256 Signature)" claim; a symmetric HS256 secret would not
    genuinely satisfy "RS256")."""

    def __init__(self, private_key: rsa.RSAPrivateKey):
        self._private_key = private_key
        self._public_key = private_key.public_key()

    @classmethod
    def generate(cls, key_size: int = 2048) -> "RS256KeyPair":
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=key_size))

    @classmethod
    def from_private_pem(cls, pem_bytes: bytes) -> "RS256KeyPair":
        key = load_pem_private_key(pem_bytes, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("PEM does not contain an RSA private key")
        return cls(key)

    def private_pem(self) -> bytes:
        return self._private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    def public_pem(self) -> bytes:
        return self._public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


def issue_jwt(claims: Dict[str, Any], keypair: RS256KeyPair, expires_in_seconds: int = 3600) -> str:
    """Real RS256-signed JWT. `claims` becomes the token payload; `exp`/
    `iat` are set here from the real current time, not caller-supplied
    (prevents a caller from minting a token that never expires)."""
    now = int(time.time())
    payload = {**claims, "iat": now, "exp": now + expires_in_seconds}
    return jwt.encode(payload, keypair.private_pem(), algorithm="RS256")


def verify_jwt(token: str, keypair: RS256KeyPair) -> Dict[str, Any]:
    """Real RS256 verification (signature + expiry). Raises
    jwt.InvalidTokenError (or a subclass — jwt.ExpiredSignatureError,
    jwt.InvalidSignatureError, etc.) on any real failure — callers should
    catch that, not assume success."""
    return jwt.decode(token, keypair.public_pem(), algorithms=["RS256"])


# ============================================================================
# Real Circuit Breaker
# ============================================================================

class CircuitState(str, Enum):
    CLOSED = "closed"        # normal operation
    OPEN = "open"             # failing fast, not calling the real function
    HALF_OPEN = "half_open"   # probing with one real call to see if recovery happened


@dataclass
class CircuitBreakerStats:
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_short_circuited: int = 0
    state_transitions: list = field(default_factory=list)


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the breaker is OPEN."""


class CircuitBreaker:
    """
    Real closed/open/half-open state machine — genuinely tracks real
    consecutive failures and real elapsed time, not a fixed on/off flag.

    - CLOSED: calls go through for real. `failure_threshold` consecutive
      real failures -> trips to OPEN.
    - OPEN: calls are rejected immediately (CircuitOpenError), no real
      call attempted, for `recovery_timeout_seconds`. This is what
      "ป้องกันระบบล่มต่อเนื่อง" (prevent cascading failure) means in
      practice — stop hammering an already-failing dependency.
    - HALF_OPEN: after the timeout, exactly one real call is allowed
      through as a probe. Real success -> CLOSED (fully recovered). Real
      failure -> back to OPEN, timer resets.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout_seconds: float = 30.0, name: str = "default"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.name = name

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None
        self.stats = CircuitBreakerStats()

    @property
    def state(self) -> CircuitState:
        # Real, lazy state transition: OPEN -> HALF_OPEN only evaluated
        # when actually queried/used, based on real elapsed wall-clock
        # time, not a background timer.
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.time() - self._opened_at >= self.recovery_timeout_seconds:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def _transition(self, new_state: CircuitState) -> None:
        self.stats.state_transitions.append({"from": self._state.value, "to": new_state.value, "at": time.time()})
        self._state = new_state
        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Real synchronous call through the breaker."""
        current = self.state
        self.stats.total_calls += 1

        if current == CircuitState.OPEN:
            self.stats.total_short_circuited += 1
            raise CircuitOpenError(f"circuit '{self.name}' is OPEN — real call rejected without attempting it")

        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        else:
            self._record_success()
            return result

    async def acall(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Real async call through the breaker (for coroutine functions)."""
        current = self.state
        self.stats.total_calls += 1

        if current == CircuitState.OPEN:
            self.stats.total_short_circuited += 1
            raise CircuitOpenError(f"circuit '{self.name}' is OPEN — real call rejected without attempting it")

        try:
            result = await fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        else:
            self._record_success()
            return result

    def _record_success(self) -> None:
        self.stats.total_successes += 1
        self._consecutive_failures = 0
        if self._state != CircuitState.CLOSED:
            self._transition(CircuitState.CLOSED)

    def _record_failure(self) -> None:
        self.stats.total_failures += 1
        self._consecutive_failures += 1
        if self._state == CircuitState.HALF_OPEN or self._consecutive_failures >= self.failure_threshold:
            self._transition(CircuitState.OPEN)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name, "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "total_calls": self.stats.total_calls, "total_successes": self.stats.total_successes,
            "total_failures": self.stats.total_failures, "total_short_circuited": self.stats.total_short_circuited,
        }


if __name__ == "__main__":
    import asyncio

    def _smoke_test_jwt():
        print("=" * 78)
        print("Layer 10 JWT RS256 smoke test")
        print("=" * 78)

        keypair = RS256KeyPair.generate()
        token = issue_jwt({"sub": "architect", "role": "owner"}, keypair, expires_in_seconds=2)
        print(f"Real RS256 token (first 40 chars): {token[:40]}...")

        claims = verify_jwt(token, keypair)
        print(f"Real verified claims: {claims}")
        assert claims["sub"] == "architect" and claims["role"] == "owner"

        # tampered token must fail
        tampered = token[:-4] + "abcd"
        try:
            verify_jwt(tampered, keypair)
            raise AssertionError("expected a tampered token to fail verification")
        except jwt.InvalidTokenError as e:
            print(f"Real tamper detection: {type(e).__name__}: {e}")

        # wrong keypair must fail
        other = RS256KeyPair.generate()
        try:
            verify_jwt(token, other)
            raise AssertionError("expected verification against the wrong public key to fail")
        except jwt.InvalidTokenError as e:
            print(f"Real wrong-key rejection: {type(e).__name__}: {e}")

        # real expiry
        print("Waiting for real token expiry (2s)...")
        time.sleep(2.5)
        try:
            verify_jwt(token, keypair)
            raise AssertionError("expected an expired token to fail verification")
        except jwt.ExpiredSignatureError as e:
            print(f"Real expiry enforcement: {e}")

        print("ALL JWT RS256 ASSERTIONS PASSED\n")

    async def _smoke_test_circuit_breaker():
        print("=" * 78)
        print("Layer 10 Circuit Breaker smoke test")
        print("=" * 78)

        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=1.0, name="test-dependency")

        call_count = {"n": 0}

        async def flaky_dependency():
            call_count["n"] += 1
            raise RuntimeError("real simulated downstream failure")

        # 3 real failures -> circuit trips OPEN
        for i in range(3):
            try:
                await breaker.acall(flaky_dependency)
            except RuntimeError:
                pass
        print(f"State after 3 real failures: {breaker.state.value}")
        assert breaker.state == CircuitState.OPEN

        # further calls are short-circuited — the real function must NOT be called
        calls_before = call_count["n"]
        try:
            await breaker.acall(flaky_dependency)
            raise AssertionError("expected CircuitOpenError")
        except CircuitOpenError as e:
            print(f"Real short-circuit: {e}")
        assert call_count["n"] == calls_before, "an OPEN circuit must not actually invoke the real function"

        print("Waiting for real recovery timeout (1s)...")
        await asyncio.sleep(1.1)
        assert breaker.state == CircuitState.HALF_OPEN, "circuit must transition to HALF_OPEN after the real timeout elapses"

        async def healthy_dependency():
            return "real recovered result"

        result = await breaker.acall(healthy_dependency)
        print(f"Real HALF_OPEN probe succeeded: {result}, new state: {breaker.state.value}")
        assert result == "real recovered result"
        assert breaker.state == CircuitState.CLOSED, "a real successful HALF_OPEN probe must close the circuit"

        print(f"Final stats: {breaker.get_stats()}")
        print("ALL CIRCUIT BREAKER ASSERTIONS PASSED")

    _smoke_test_jwt()
    asyncio.run(_smoke_test_circuit_breaker())
