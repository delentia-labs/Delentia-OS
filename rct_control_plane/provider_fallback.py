"""
Round 57: a backup model when the chosen one fails (Hermes: fallback providers).

An always-on agent that stops answering whenever one provider has a bad hour is not always-on. `DELENTIA_FALLBACK_MODELS` names backups, tried in order when a
call to the current model fails for a reason that another model might not share:

    DELENTIA_FALLBACK_MODELS="openrouter:qwen/qwen3-235b-a22b-2507,ollama:qwen2.5:7b"

A switch happens on: an open circuit breaker, a network error, a timeout, an HTTP 5xx/429/408. It does NOT happen on a bad request, a refused budget or a
refused sovereignty decision (those are about the request or the owner's rules, not about the provider, and another model would be asked the same thing).

A backup is allowed to exist only if it can never make the situation worse, because the guards that sit around the provider (the sovereignty policy and the
per-episode budget) were built for the PRIMARY model:
  * it must expose data no more than the primary does: hosting kind local < in-region < cross-border, and it must itself be allowed by the sovereignty policy (so a
    local backup for a cloud primary is fine, a cloud backup for a local primary is dropped, because PII that was fine to send to a local model might not be fine to send out);
  * when a cost budget is set, the meter prices every call at the DEAREST model in the chain, and a backup whose price is unknown is dropped (a budget that cannot be
    checked is not a budget);
  * every switch is written to the audit trail (`model_fallback`), so the Governance page shows when and why the answer came from a different model.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator, Callable, List, Optional, Tuple

from rct_control_plane.llm_provider import LLMProvider, LLMUsage

FALLBACK_ENV = "DELENTIA_FALLBACK_MODELS"
_RANK = {"local": 0, "in_region": 1, "cross_border": 2}


def switchable(exc: BaseException) -> bool:
    """Would a different model plausibly not fail the same way?"""
    import httpx
    from rct_control_plane.provider_breaker import ProviderUnavailable
    if isinstance(exc, (ProviderUnavailable, asyncio.TimeoutError, httpx.TransportError, httpx.TimeoutException, ConnectionError, TimeoutError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code in (408, 429)
    return False


class FallbackProvider(LLMProvider):
    def __init__(self, members: List[LLMProvider], on_switch: Optional[Callable[[str, str, str], None]] = None) -> None:
        if not members:
            raise ValueError("a fallback chain needs at least one provider")
        self._members = members
        self._active = 0
        self._on_switch = on_switch

    @property
    def inner(self) -> LLMProvider:
        """The PRIMARY: what the sovereignty guard around this provider judges (the backups are filtered so they can never expose more)."""
        return self._members[0]

    @property
    def active(self) -> LLMProvider:
        return self._members[self._active]

    @property
    def model(self) -> str:
        return str(getattr(self.active, "model", "?"))

    @property
    def last_usage(self) -> Optional[LLMUsage]:               # type: ignore[override]
        return self.active.last_usage

    @last_usage.setter
    def last_usage(self, value: Optional[LLMUsage]) -> None:
        self.active.last_usage = value

    def _announce(self, failed: LLMProvider, nxt: LLMProvider, exc: BaseException) -> None:
        if self._on_switch is not None:
            try:
                self._on_switch(str(getattr(failed, "model", "?")), str(getattr(nxt, "model", "?")), f"{type(exc).__name__}: {str(exc)[:120]}")
            except Exception:                                  # noqa: BLE001 - reporting a switch must never decide whether the call is made
                pass

    async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7,
                       max_tokens: int = 2048, json_mode: bool = False) -> str:
        last: Optional[BaseException] = None
        for index in range(self._active, len(self._members)):
            member = self._members[index]
            try:
                reply = await member.complete(prompt, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode)
                self._active = index                           # the next call goes to the model that just worked
                return reply
            except Exception as exc:                           # noqa: BLE001 - classified just below
                if not switchable(exc) or index == len(self._members) - 1:
                    raise
                last = exc
                self._announce(member, self._members[index + 1], exc)
        raise last or RuntimeError("no provider answered")

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7,
                              max_tokens: int = 2048) -> AsyncIterator[str]:
        # Only before the first piece has been produced can another model take over without the reader seeing a seam.
        for index in range(self._active, len(self._members)):
            member = self._members[index]
            started = False
            try:
                async for piece in member.stream_complete(prompt, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens):
                    started = True
                    yield piece
                self._active = index
                return
            except Exception as exc:                           # noqa: BLE001
                if started or not switchable(exc) or index == len(self._members) - 1:
                    raise
                self._announce(member, self._members[index + 1], exc)


def configured() -> List[Tuple[str, str]]:
    """[(provider, model)] from DELENTIA_FALLBACK_MODELS; malformed items are ignored (and never raise)."""
    out: List[Tuple[str, str]] = []
    for item in (os.environ.get(FALLBACK_ENV) or "").split(","):
        provider, _, model = item.strip().partition(":")
        if provider.strip().lower() in ("ollama", "openrouter") and model.strip():
            out.append((provider.strip().lower(), model.strip()))
    return out


def _build(provider: str, model: str) -> Optional[LLMProvider]:
    from rct_control_plane.llm_provider import OllamaProvider, OpenRouterProvider
    if provider == "openrouter":
        return OpenRouterProvider(model=model) if os.environ.get("OPENROUTER_API_KEY") else None      # no key: it could never answer
    return OllamaProvider(model=model)


def chain(primary: LLMProvider, base: LLMProvider, persistence: Any = None, namespace: str = "", cost_budget_set: bool = False,
          price_of: Optional[Callable[[LLMProvider], Optional[Tuple[float, float]]]] = None) -> Tuple[LLMProvider, Optional[Tuple[float, float]], List[str]]:
    """(provider to use, worst-case prices when a cost budget is set, notes about backups that were dropped).

    `primary` is the breaker-wrapped primary; `base` is the unwrapped one (what the guard and the price lookup understand). With no backups configured this returns
    `primary` unchanged, so turning the feature off is not a different code path."""
    from rct_control_plane import provider_breaker, residency
    wanted = configured()
    if not wanted:
        return primary, None, []
    notes: List[str] = []
    members: List[LLMProvider] = [primary]
    policy = residency.load_policy()
    base_rank = _RANK.get(residency.hosting_for_provider(base).kind, 2)
    prices = price_of(base) if (cost_budget_set and price_of) else None
    for name, model in wanted:
        member = _build(name, model)
        if member is None:
            notes.append(f"{name}:{model}: not used (no API key)")
            continue
        hosting = residency.hosting_for_provider(member)
        if _RANK.get(hosting.kind, 2) > base_rank:
            notes.append(f"{name}:{model}: dropped, it would expose data more than the primary model does ({hosting.kind})")
            continue
        if policy is not None:
            from core.regional_adapter.sovereignty import evaluate_call
            if evaluate_call(policy, hosting, "").action != "allow":
                notes.append(f"{name}:{model}: dropped, the sovereignty policy does not allow it")
                continue
        if cost_budget_set:
            member_price = price_of(member) if price_of else None
            if member_price is None:
                notes.append(f"{name}:{model}: dropped, its price is unknown and a cost budget is set")
                continue
            prices = (max(prices[0], member_price[0]), max(prices[1], member_price[1])) if prices else member_price
        members.append(provider_breaker.wrap(member))
    if len(members) == 1:
        return primary, prices, notes

    def announce(failed: str, nxt: str, reason: str) -> None:
        if persistence is not None:
            persistence.append_audit(entity_type="model_fallback", entity_id=f"{namespace}-{failed}", action="switched", actor=namespace or "runtime",
                                     changes={"from": failed, "to": nxt, "reason": reason})
    return FallbackProvider(members, on_switch=announce), prices, notes
