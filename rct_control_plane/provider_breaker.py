"""
A circuit breaker around the model provider (Round 53).

Layer 10 of the architecture document promises a circuit breaker "to stop an outage cascading". The class
existed (enterprise_hardening.CircuitBreaker, with a smoke test) but nothing used it: a model endpoint that was
down was retried by every episode, each one waiting out its own timeouts and retries.

CircuitBreakerProvider wraps the provider the governed loop is about to meter. After
DELENTIA_LLM_BREAKER_THRESHOLD consecutive failures (default 5) calls are refused at once for
DELENTIA_LLM_BREAKER_RECOVERY seconds (default 30), then one probe is let through; a success closes the
circuit again. The state is shared by every loop in the process for the same endpoint and model, which is the
point: the second episode should not have to rediscover that the endpoint is down.

An open circuit raises ProviderUnavailable. The loop does not retry that (waiting would only repeat the
failure) and ends the episode with stopped_reason "llm_error" and a note that says the circuit is open.
Set DELENTIA_LLM_BREAKER=0 to turn it off.
"""
from __future__ import annotations

import os
import time
from typing import Any, AsyncIterator, Dict, Optional, Tuple

from rct_control_plane.enterprise_hardening import CircuitBreaker, CircuitOpenError, CircuitState
from rct_control_plane.llm_provider import LLMProvider, LLMUsage

BREAKER_ENV = "DELENTIA_LLM_BREAKER"
THRESHOLD_ENV = "DELENTIA_LLM_BREAKER_THRESHOLD"
RECOVERY_ENV = "DELENTIA_LLM_BREAKER_RECOVERY"


class ProviderUnavailable(RuntimeError):
    """The model endpoint has failed repeatedly and is not being called for now."""


_registry: Dict[Tuple[str, str, str], CircuitBreaker] = {}


def _number(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def breaker_for(provider: Any) -> CircuitBreaker:
    """The shared breaker for this endpoint and model (created on first use with the current settings)."""
    key = (type(provider).__name__, str(getattr(provider, "model", "")),
           str(getattr(provider, "base_url", None) or getattr(provider, "llm_url", "")))
    if key not in _registry:
        _registry[key] = CircuitBreaker(failure_threshold=max(1, int(_number(THRESHOLD_ENV, 5))),
                                        recovery_timeout_seconds=max(0.0, _number(RECOVERY_ENV, 30.0)), name="/".join(key[:2]))
    return _registry[key]


def reset_all() -> None:
    _registry.clear()


class CircuitBreakerProvider(LLMProvider):
    def __init__(self, inner: LLMProvider, breaker: Optional[CircuitBreaker] = None):
        self._inner = inner
        self.breaker = breaker or breaker_for(inner)

    @property
    def inner(self) -> LLMProvider:
        return self._inner

    @property
    def model(self) -> str:
        return str(getattr(self._inner, "model", "?"))

    @property
    def last_usage(self) -> Optional[LLMUsage]:               # type: ignore[override]
        return self._inner.last_usage

    @last_usage.setter
    def last_usage(self, value: Optional[LLMUsage]) -> None:
        self._inner.last_usage = value

    def _unavailable(self) -> ProviderUnavailable:
        wait = 0.0
        if self.breaker._opened_at is not None:
            wait = max(0.0, self.breaker.recovery_timeout_seconds - (time.time() - self.breaker._opened_at))
        return ProviderUnavailable(f"the model endpoint failed {self.breaker.failure_threshold} times in a row; "
                                   f"calls are paused for another {wait:.0f} s (circuit open)")

    async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7,
                       max_tokens: int = 2048, json_mode: bool = False) -> str:
        try:
            return await self.breaker.acall(self._inner.complete, prompt, system_prompt=system_prompt, temperature=temperature,
                                            max_tokens=max_tokens, json_mode=json_mode)
        except CircuitOpenError as exc:
            raise self._unavailable() from exc

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7,
                              max_tokens: int = 2048) -> AsyncIterator[str]:
        if self.breaker.state == CircuitState.OPEN:
            self.breaker.stats.total_short_circuited += 1
            raise self._unavailable()
        try:
            async for piece in self._inner.stream_complete(prompt, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens):
                yield piece
        except Exception:
            self.breaker._record_failure()
            raise
        else:
            self.breaker._record_success()


def wrap(provider: LLMProvider) -> LLMProvider:
    """The provider with a breaker around it, unless DELENTIA_LLM_BREAKER=0."""
    if (os.environ.get(BREAKER_ENV) or "1").strip().lower() in ("0", "false", "no", "off"):
        return provider
    if isinstance(provider, CircuitBreakerProvider):
        return provider
    return CircuitBreakerProvider(provider)
