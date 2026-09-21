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
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import httpx

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
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
    def __init__(self, llm_url: str = DEFAULT_OLLAMA_URL, model: str = "qwen2.5:7b"):
        self.llm_url = llm_url
        self.model = model

    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {"model": self.model, "prompt": full_prompt, "stream": False,
                   "options": {"temperature": temperature}}
        if json_mode:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(f"{self.llm_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()["response"]

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None,
                               temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Real token streaming via Ollama's own `stream: true` mode -
        the response body is real newline-delimited JSON, one object per
        real generated chunk (`{"response": "...", "done": false}`,
        ending with a final `{"done": true, ...}`)."""
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {"model": self.model, "prompt": full_prompt, "stream": True,
                   "options": {"temperature": temperature}}
        async with httpx.AsyncClient(timeout=90.0) as client:
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
            self.model, prompt, system_prompt, temperature, max_tokens, json_mode, self.compat,
        )
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

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
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream(
                "POST", "https://openrouter.ai/api/v1/chat/completions",
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


def get_default_provider() -> LLMProvider:
    choice = os.getenv("DELENTIA_LLM_PROVIDER", "ollama").lower()
    if choice == "openrouter":
        if os.getenv("OPENROUTER_API_KEY"):
            return OpenRouterProvider()
        logger.warning("DELENTIA_LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is unset; falling back to Ollama")
    return OllamaProvider()


class QuotaExceededError(Exception):
    """Real quota enforcement (Round 24 Task 31) - the one real,
    feasible slice of the master doc's HRM Controller "API Quota"
    dimension this session can actually measure (VRAM/CPU/bandwidth
    monitoring is out of scope - not claimed)."""


@dataclass
class QuotaTracker:
    max_calls_per_provider: dict = None
    _call_counts: dict = None

    def __post_init__(self):
        if self.max_calls_per_provider is None:
            self.max_calls_per_provider = {}
        if self._call_counts is None:
            self._call_counts = {}

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
