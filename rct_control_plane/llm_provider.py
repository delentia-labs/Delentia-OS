"""
Model-agnostic LLM provider abstraction (Round 22 Phase 10).

Consolidates the interface only - existing call sites
(algo_09_reflexion_plus.py, algo_32_mctr.py, openrouter_client.py,
signedai/openrouter_client.py) are left as-is per Zero-Delete; NEW code
(autonomous_loop.py, after this module wires in) uses this instead of a
5th hardcoded convention.
"""
from __future__ import annotations

import json
import logging
import re
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncIterator, Optional

if TYPE_CHECKING:
    from rct_control_plane.topic_cache import TopicCache

import httpx  # noqa: F401 - kept: tests and callers patch llm_provider.httpx
from rct_control_plane import http_client

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

# Real, confirmed need (2026-09-23): GitHub Actions' hosted CI runners are
# CPU-only (no GPU), and a 7B model's real inference time for these tests'
# actual prompts genuinely exceeds a 90s budget there even with the model
# already warmed/resident in memory - confirmed by two separate real CI
# runs both failing with httpx.ReadTimeout, not ConnectError, after a
# real Ollama service container was already reachable and warmed. 90.0
# stays the default for real production/local use (unchanged - a real
# user's machine, or a GPU-backed deployment, doesn't need this widened);
# CI sets DELENTIA_OLLAMA_TIMEOUT_S in .github/workflows/ci.yml instead of
# this default being silently loosened for everyone.
OLLAMA_TIMEOUT_S = float(os.getenv("DELENTIA_OLLAMA_TIMEOUT_S", "90.0"))

logger = logging.getLogger(__name__)


@dataclass
class LLMUsage:
    """Round 50: what one model call used. cost_usd None = not known."""
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Optional[float]


class LLMProvider(ABC):
    # Round 50: set by complete() when the backend reports usage.
    last_usage: Optional[LLMUsage] = None

    @abstractmethod
    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        ...

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None,
                               temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Round 39: real token streaming - default implementation for
        any provider that doesn't override this (Zero-Delete: no
        existing provider is forced to implement it) falls back to one
        single "chunk" containing the whole completion, honestly not a
        real stream. OllamaProvider/OpenRouterProvider below override
        this with genuine incremental yielding from each provider's own
        real streaming API. Deliberately has NO json_mode parameter -
        streaming is for free-text answers (see autonomous_loop.py's
        real use of this for AutonomousLoop's final-answer generation),
        not the structured decision JSON decide_next_action() parses,
        which still needs one complete, parseable response."""
        yield await self.complete(prompt, system_prompt, temperature, max_tokens, json_mode=False)


class OllamaProvider(LLMProvider):
    # Round 44 item I.3: only calls at or below this temperature are
    # cached. 0.3 is not an arbitrary new number - it's the real
    # temperature autonomous_loop.py's decide_next_action() already uses
    # for its JSON-mode tool-selection call (the one real low-temperature,
    # deterministic-ish call site that exists in this codebase today).
    # Calls above this threshold are intentionally left uncached - a
    # high-temperature call is asking for real sampling diversity, and
    # caching it would silently defeat that.
    _CACHEABLE_TEMPERATURE_MAX = 0.3
    _CACHE_TTL_SECONDS = 3600.0

    def __init__(self, llm_url: str = DEFAULT_OLLAMA_URL, model: str = "qwen2.5:7b",
                 cache: Optional["TopicCache"] = None):
        self.llm_url = llm_url
        self.model = model
        self.cache = cache

    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        # A local `cache` binding (rather than repeated `self.cache` checks)
        # so mypy can actually narrow Optional[TopicCache] -> TopicCache at
        # each real call site below - `self.cache` is a mutable attribute,
        # so mypy never trusts a narrowing derived from it to still hold a
        # few lines later, even behind an `if cacheable:` guard computed
        # from the exact same check (a real error CI caught: "Item None of
        # TopicCache | None has no attribute get/put").
        cache = self.cache
        cacheable = cache is not None and temperature <= self._CACHEABLE_TEMPERATURE_MAX

        if cacheable and cache is not None:
            cached = cache.get(full_prompt, full_prompt)
            if cached is not None:
                self.last_usage = LLMUsage(0, 0, 0.0)
                return cached

        payload = {"model": self.model, "prompt": full_prompt, "stream": False,
                   "options": {"temperature": temperature}}
        if json_mode:
            payload["format"] = "json"
        async with http_client.async_client(timeout=OLLAMA_TIMEOUT_S) as client:
            response = await client.post(f"{self.llm_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            result = data["response"]
        # Ollama reports prompt_eval_count / eval_count; a local model costs nothing per call.
        self.last_usage = LLMUsage(int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0), 0.0)

        if cacheable and cache is not None:
            cache.put(full_prompt, full_prompt, result, ttl_seconds=self._CACHE_TTL_SECONDS)
        return result

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None,
                               temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Real token streaming via Ollama's own `stream: true` mode -
        the response body is real newline-delimited JSON, one object per
        real generated chunk (`{"response": "...", "done": false}`,
        ending with a final `{"done": true, ...}`)."""
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {"model": self.model, "prompt": full_prompt, "stream": True,
                   "options": {"temperature": temperature}}
        async with http_client.async_client(timeout=OLLAMA_TIMEOUT_S) as client:
            async with client.stream("POST", f"{self.llm_url}/api/generate", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    text = chunk.get("response", "")
                    if text:
                        yield text
                    if chunk.get("done"):
                        break


@dataclass
class CompatProfile:
    """Real gateway-quirk handling (Round 23 Phase 12 Task 28) — mirrors
    DeepSeek Harness's own real, researched supportsDeveloperRole/
    maxTokensField flags: different OpenAI-compatible gateways reject
    different request shapes for the exact same logical request."""
    supports_developer_role: bool = True
    max_tokens_field: str = "max_tokens"


def _build_openrouter_payload(
    model: str, prompt: str, system_prompt: Optional[str], temperature: float,
    max_tokens: int, json_mode: bool, compat: CompatProfile,
) -> dict:
    """Pure payload construction, extracted so Task 28's compat behavior
    is unit-testable without a real network call."""
    messages = []
    if system_prompt:
        if compat.supports_developer_role:
            messages.append({"role": "system", "content": system_prompt})
        else:
            prompt = f"{system_prompt}\n\n{prompt}"
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "temperature": temperature,
               compat.max_tokens_field: max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


OPENROUTER_DEFAULT_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_BASE_ENV = "DELENTIA_OPENROUTER_BASE_URL"


def openrouter_base_url() -> str:
    """Where OpenRouter calls go. The default is OpenRouter itself. DELENTIA_OPENROUTER_BASE_URL may point at a loopback server (a rehearsal
    of the paid test against a fake: scripts/rehearse_full_test.py) or at another openrouter.ai address; anything else is ignored, because
    the API key is sent to whatever this returns."""
    override = (os.environ.get(OPENROUTER_BASE_ENV) or "").strip().rstrip("/")
    if override:
        loopback = re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)", override)
        if override.startswith("https://openrouter.ai/") or loopback:
            return override
        logging.getLogger(__name__).warning("%s ignored: only https://openrouter.ai/... or a loopback address is accepted", OPENROUTER_BASE_ENV)
    return OPENROUTER_DEFAULT_BASE


# Models (as OpenRouter ids) that answered HTTP 400 to `response_format` in this process: later calls do not send it. OpenRouter routes to
# many upstream providers and not all of them accept JSON mode; the loop's prompt already asks for JSON, so dropping the parameter costs
# some reliability, not the call.
_NO_JSON_MODE: set = set()


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "anthropic/claude-sonnet-5",
                 compat: Optional[CompatProfile] = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouterProvider requires OPENROUTER_API_KEY (arg or env var)")
        self.model = model
        self.compat = compat or CompatProfile()

    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        payload = _build_openrouter_payload(
            self.model, prompt, system_prompt, temperature, max_tokens, json_mode and self.model not in _NO_JSON_MODE, self.compat,
        )
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with http_client.async_client(timeout=90.0) as client:
            response = await client.post(f"{openrouter_base_url()}/chat/completions", headers=headers, json=payload)
            if getattr(response, "status_code", 200) == 400 and "response_format" in payload:
                # This model (or the upstream provider it was routed to) does not take JSON mode: remember that and ask again without it.
                _NO_JSON_MODE.add(self.model)
                payload.pop("response_format")
                response = await client.post(f"{openrouter_base_url()}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        self.last_usage = LLMUsage(int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0),
                                   float(cost) if isinstance(cost, (int, float)) else None)
        return data["choices"][0]["message"]["content"]

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None,
                               temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Real token streaming via OpenRouter's OpenAI-compatible SSE
        mode (`"stream": True`) - real `data: {...}` lines, each with a
        real incremental `choices[0]["delta"]["content"]` fragment,
        terminated by the real literal `data: [DONE]` sentinel line."""
        payload = _build_openrouter_payload(
            self.model, prompt, system_prompt, temperature, max_tokens, json_mode=False, compat=self.compat,
        )
        payload["stream"] = True
        async with http_client.async_client(timeout=90.0) as client:
            async with client.stream(
                "POST", f"{openrouter_base_url()}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    if not data:
                        continue
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text


class OpenAICompatibleProvider(LLMProvider):
    """Round 52, plug-and-play national AI: any endpoint that speaks the OpenAI chat
    completions protocol - a national provider's API, vLLM, llama.cpp server, LM Studio,
    a self-hosted gateway - declared with where it processes data.

    `kind`/`region` are the operator's declaration (see core/regional_adapter/
    sovereignty.py): "local" for the tenant's own machine or network, "in_region" with
    an ISO country code for a provider hosted in that country, "cross_border"
    otherwise. The residency guard trusts the declaration, so it belongs in the
    contract with the provider, not in a guess. The key is read from the environment
    variable NAMED by `credential_env`; it is never stored."""

    def __init__(self, base_url: str, model: str, credential_env: Optional[str] = None, kind: str = "cross_border",
                 region: str = "", operator: str = "", compat: Optional[CompatProfile] = None, timeout: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.credential_env = credential_env
        self.kind = kind
        self.region = region.upper()
        self.operator = operator
        self.compat = compat or CompatProfile()
        self.timeout = timeout

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        key = os.getenv(self.credential_env) if self.credential_env else None
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        payload = _build_openrouter_payload(self.model, prompt, system_prompt, temperature, max_tokens, json_mode, self.compat)
        async with http_client.async_client(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        usage = data.get("usage") or {}
        # A self-hosted or national endpoint reports no price; unknown cost stays None.
        self.last_usage = LLMUsage(int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0), None)
        return data["choices"][0]["message"]["content"]

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None,
                               temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        payload = _build_openrouter_payload(self.model, prompt, system_prompt, temperature, max_tokens, False, self.compat)
        payload["stream"] = True
        async with http_client.async_client(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    if not data:
                        continue
                    text = json.loads(data).get("choices", [{}])[0].get("delta", {}).get("content")
                    if text:
                        yield text


def get_default_provider(profile: Optional[str] = None) -> LLMProvider:
    """Round 48: provider AND model now come from model_config's
    resolution chain (args > env DELENTIA_LLM_PROVIDER/DELENTIA_LLM_MODEL
    > profile config > config default > builtin), so a user can pick any
    model without code changes. With no env and no config file this
    resolves to exactly the pre-Round-48 behaviour (Ollama qwen2.5:7b)."""
    from rct_control_plane.model_config import BUILTIN_DEFAULT_MODELS, resolve_model_selection

    selection = resolve_model_selection(profile=profile)
    if selection.provider == "openai-compat":
        from rct_control_plane.model_config import openai_compat_settings
        endpoint = openai_compat_settings()
        return OpenAICompatibleProvider(
            base_url=endpoint["base_url"], model=selection.model, credential_env=endpoint.get("credential_env"),
            kind=endpoint.get("kind", "cross_border"), region=endpoint.get("region", ""), operator=endpoint.get("operator", ""),
        )
    if selection.provider == "openrouter":
        if os.getenv("OPENROUTER_API_KEY"):
            return OpenRouterProvider(model=selection.model)
        logger.warning(
            "model selection is openrouter:%s but OPENROUTER_API_KEY is unset; falling back to Ollama %s",
            selection.model, BUILTIN_DEFAULT_MODELS["ollama"],
        )
        return OllamaProvider(model=BUILTIN_DEFAULT_MODELS["ollama"])
    return OllamaProvider(model=selection.model)


class QuotaExceededError(Exception):
    """Real quota enforcement (Round 24 Task 31) - the one real,
    feasible slice of the master doc's HRM Controller "API Quota"
    dimension this session can actually measure (VRAM/CPU/bandwidth
    monitoring is out of scope - not claimed)."""


@dataclass
class QuotaTracker:
    # field(default_factory=dict), not `= None` + __post_init__: the real
    # intent here is "always a dict, never actually None" (every real use
    # below calls .get()/indexes it with no None-check) - the old
    # `dict = None` default was an implicit-Optional PEP 484 violation
    # mypy no longer allows, and giving it a real Optional[dict] type
    # instead would have made every one of those real call sites need an
    # unnecessary None-check for a state that can't occur post-__init__.
    max_calls_per_provider: dict = field(default_factory=dict)
    _call_counts: dict = field(default_factory=dict)

    def check_quota(self, provider_name: str) -> bool:
        limit = self.max_calls_per_provider.get(provider_name)
        if limit is None:
            return True
        return self._call_counts.get(provider_name, 0) < limit

    def record_call(self, provider_name: str) -> None:
        self._call_counts[provider_name] = self._call_counts.get(provider_name, 0) + 1


class QuotaCheckedProvider(LLMProvider):
    """Wraps any real LLMProvider with real, in-memory quota
    enforcement - raises before making a real network call once the
    configured limit is reached, never after."""

    def __init__(self, inner: LLMProvider, provider_name: str, quota: QuotaTracker):
        self._inner = inner
        self._provider_name = provider_name
        self._quota = quota

    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        if not self._quota.check_quota(self._provider_name):
            raise QuotaExceededError(f"quota exceeded for provider '{self._provider_name}'")
        self._quota.record_call(self._provider_name)
        return await self._inner.complete(prompt, system_prompt, temperature, max_tokens, json_mode)

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None,
                               temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        if not self._quota.check_quota(self._provider_name):
            raise QuotaExceededError(f"quota exceeded for provider '{self._provider_name}'")
        self._quota.record_call(self._provider_name)
        async for chunk in self._inner.stream_complete(prompt, system_prompt, temperature, max_tokens):
            yield chunk


class BudgetExceededError(Exception):
    """Round 50: raised BEFORE a model call that could take an episode over
    its token or cost budget, so the call is never made."""


class ResidencyViolation(Exception):
    """Round 52: raised BEFORE a model call whose data the tenant's sovereignty
    policy does not allow to go where the call would send it. Nothing was sent."""


def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except ImportError:
        return max(1, -(-len(text) // 4))


class MeteredProvider(LLMProvider):
    """Round 50 (Round 48 end-point criterion 7, "know the cost in
    advance"): wraps one episode's provider, adds up what each call used,
    and refuses a call whose worst case (prompt tokens + max_tokens) would
    exceed the remaining budget.

    Prices are USD per million tokens. A local Ollama model costs 0. When a
    cost budget is set but the model's price is unknown, calls are refused:
    a budget that cannot be checked is not a budget (fail closed)."""

    def __init__(self, inner: LLMProvider, max_cost_usd: Optional[float] = None,
                 max_tokens_total: Optional[int] = None,
                 prompt_price_per_mtok: Optional[float] = None,
                 completion_price_per_mtok: Optional[float] = None):
        self._inner = inner
        self.max_cost_usd = max_cost_usd
        self.max_tokens_total = max_tokens_total
        if isinstance(inner, OllamaProvider) and prompt_price_per_mtok is None and completion_price_per_mtok is None:
            prompt_price_per_mtok = completion_price_per_mtok = 0.0
        self.prompt_price_per_mtok = prompt_price_per_mtok
        self.completion_price_per_mtok = completion_price_per_mtok
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0
        self.cost_known = True
        self.refused: Optional[str] = None

    @property
    def inner(self) -> LLMProvider:
        return self._inner

    @property
    def model(self) -> str:
        return str(getattr(self._inner, "model", "?"))

    def _price(self, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
        if self.prompt_price_per_mtok is None or self.completion_price_per_mtok is None:
            return None
        return (prompt_tokens * self.prompt_price_per_mtok
                + completion_tokens * self.completion_price_per_mtok) / 1_000_000

    def _check_budget(self, prompt_text: str, max_tokens: int) -> None:
        worst_prompt = _count_tokens(prompt_text)
        if self.max_tokens_total is not None:
            used = self.prompt_tokens + self.completion_tokens
            if used + worst_prompt + max_tokens > self.max_tokens_total:
                self.refused = (f"token budget: {used} used + up to {worst_prompt + max_tokens} for this call "
                                f"> {self.max_tokens_total}")
                raise BudgetExceededError(self.refused)
        if self.max_cost_usd is not None:
            worst = self._price(worst_prompt, max_tokens)
            if worst is None or not self.cost_known:
                self.refused = f"cost budget ${self.max_cost_usd} is set but the price of {self.model} is unknown"
                raise BudgetExceededError(self.refused)
            if self.cost_usd + worst > self.max_cost_usd:
                self.refused = (f"cost budget: ${self.cost_usd:.6f} spent + up to ${worst:.6f} for this call "
                                f"> ${self.max_cost_usd}")
                raise BudgetExceededError(self.refused)

    def _record(self, prompt_text: str, completion_text: str) -> None:
        usage = self._inner.last_usage
        self._inner.last_usage = None
        if usage is None or (usage.prompt_tokens == 0 and usage.completion_tokens == 0 and usage.cost_usd is None):
            usage = LLMUsage(_count_tokens(prompt_text), _count_tokens(completion_text), None)
        cost = usage.cost_usd if usage.cost_usd is not None else self._price(usage.prompt_tokens,
                                                                               usage.completion_tokens)
        self.calls += 1
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        if cost is None:
            self.cost_known = False
        else:
            self.cost_usd += cost
        self.last_usage = LLMUsage(usage.prompt_tokens, usage.completion_tokens, cost)

    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        self._check_budget(full, max_tokens)
        result = await self._inner.complete(prompt, system_prompt, temperature, max_tokens, json_mode)
        self._record(full, result)
        return result

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None,
                               temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        self._check_budget(full, max_tokens)
        chunks = []
        async for chunk in self._inner.stream_complete(prompt, system_prompt, temperature, max_tokens):
            chunks.append(chunk)
            yield chunk
        self._inner.last_usage = None  # streamed responses carry no usage here; estimate instead
        self._record(full, "".join(chunks))

    def summary(self) -> dict:
        return {
            "model": self.model,
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6) if self.cost_known else None,
            "cost_known": self.cost_known,
            "max_cost_usd": self.max_cost_usd,
            "max_tokens_total": self.max_tokens_total,
            "refused": self.refused,
        }
