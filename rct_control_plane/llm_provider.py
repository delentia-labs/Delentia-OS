"""
Model-agnostic LLM provider abstraction (Round 22 Phase 10).

Consolidates the interface only - existing call sites
(algo_09_reflexion_plus.py, algo_32_mctr.py, openrouter_client.py,
signedai/openrouter_client.py) are left as-is per Zero-Delete; NEW code
(autonomous_loop.py, after this module wires in) uses this instead of a
5th hardcoded convention.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system_prompt: Optional[str] = None,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        json_mode: bool = False) -> str:
        ...


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


def get_default_provider() -> LLMProvider:
    choice = os.getenv("DELENTIA_LLM_PROVIDER", "ollama").lower()
    if choice == "openrouter":
        if os.getenv("OPENROUTER_API_KEY"):
            return OpenRouterProvider()
        logger.warning("DELENTIA_LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is unset; falling back to Ollama")
    return OllamaProvider()
