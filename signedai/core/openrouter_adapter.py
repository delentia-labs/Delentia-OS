"""
OpenRouter Adapter — real HTTP client for the 7 HexaCore roles that were
declared in the registry with real OpenRouter model IDs but had zero real
API-calling code anywhere in the codebase (Round 32).

Round 31's SignedAI Layer 8 audit found that of HexaCoreRegistry's 10
declared roles, only GROQ_ADAPTER and OLLAMA_ADAPTER had real HTTP client
implementations (groq_adapter.py, ollama_fallback.py). The other 7 roles
(SUPREME_ARCHITECT, LEAD_BUILDER, JUNIOR_BUILDER, SPECIALIST, LIBRARIAN,
HUMANIZER, REGIONAL_THAI) declared real OpenRouter model IDs in ModelInfo
but had no code that could ever actually call them.

Design mirrors groq_adapter.py exactly:
  - HTTP-only (urllib.request, no SDK dependency)
  - Honest Unavailable/Error exception pair - never fabricates a response
  - Respects signedai's own stated "no dependency on rct_platform private
    internals" design constraint (registry.py's module docstring) - does
    NOT import rct_control_plane.llm_provider, even though that module
    already has its own separate OpenRouterProvider for a different part
    of the codebase.

A real OPENROUTER_API_KEY is required for `generate()`/`call_hexacore_role`
to make a live call. Round 32 confirmed OPENROUTER_API_KEY is not set as
an environment variable in this dev environment - is_configured() lets a
caller check honestly before attempting a call, and the payload-building
logic is unit-testable with zero network access via _build_payload().
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from signedai.core.registry import HexaCoreRegistry, HexaCoreRole

OPENROUTER_API_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MAX_TOKENS = 512

_OPENROUTER_GENERATE_TIMEOUT = 30  # seconds


class OpenRouterUnavailableError(RuntimeError):
    """Raised when no API key is configured - never attempts a network call."""


class OpenRouterGenerateError(RuntimeError):
    """Raised when the OpenRouter /chat/completions call fails."""


def _build_payload(model_id: str, prompt: str, system_prompt: Optional[str], max_tokens: int) -> dict:
    """Real, network-independent payload construction - split out so it's
    unit-testable without a live call, same rationale as llm_provider.py's
    own _build_openrouter_payload (Round 23)."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
    }


class OpenRouterAdapter:
    """Thin HTTP adapter for a single OpenRouter-routed model."""

    def __init__(
        self,
        model_id: str,
        api_key: Optional[str] = None,
        base_url: str = OPENROUTER_API_URL,
        generate_timeout: int = _OPENROUTER_GENERATE_TIMEOUT,
    ) -> None:
        self.model_id = model_id
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._timeout = generate_timeout

    def is_configured(self) -> bool:
        """Honest check before calling - never silently fabricates a
        response when no key is present."""
        return bool(self._api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 max_tokens: int = OPENROUTER_DEFAULT_MAX_TOKENS) -> str:
        """
        Call OpenRouter /chat/completions and return the assistant message.

        Raises:
            OpenRouterUnavailableError: if no API key is configured.
            OpenRouterGenerateError: if the API call fails or errors.
        """
        if not self.is_configured():
            raise OpenRouterUnavailableError(
                f"OPENROUTER_API_KEY not configured - cannot call {self.model_id}."
            )

        body = json.dumps(_build_payload(self.model_id, prompt, system_prompt, max_tokens)).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise OpenRouterGenerateError(f"OpenRouter HTTP {e.code} for {self.model_id}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise OpenRouterGenerateError(f"OpenRouter unreachable for {self.model_id}: {e.reason}") from e

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise OpenRouterGenerateError(f"Unexpected OpenRouter response shape for {self.model_id}: {data}") from e


def call_hexacore_role(role: HexaCoreRole, prompt: str, system_prompt: Optional[str] = None,
                        api_key: Optional[str] = None, max_tokens: int = OPENROUTER_DEFAULT_MAX_TOKENS) -> str:
    """Real convenience wrapper: resolves the role's real OpenRouter model
    ID from the registry, then calls it. Raises OpenRouterUnavailableError
    honestly when no key is configured - never fabricates a response."""
    model_id = HexaCoreRegistry.get_model_id(role)
    adapter = OpenRouterAdapter(model_id, api_key=api_key)
    return adapter.generate(prompt, system_prompt=system_prompt, max_tokens=max_tokens)
