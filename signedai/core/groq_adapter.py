"""
Groq LPU Adapter — Ultra-Low-Latency Inference via Groq REST API

Groq LPU (Language Processing Unit) provides token-generation speeds
significantly higher than GPU-based inference. This adapter slots into
the HexaCore fallback chain as the GROQ_ADAPTER role.

Design mirrors ollama_fallback.py:
  - HTTP-only (no groq-sdk dependency)
  - Patched in tests via unittest.mock.patch("urllib.request.urlopen")
  - 3-tier chain: primary_fn → GroqAdapter → RegexFallback

GROQ_FALLBACK_VERSION = "1.0"
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Callable, Optional

GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1"
GROQ_FALLBACK_VERSION = "1.0"

_GROQ_CONNECT_TIMEOUT = 5     # seconds — quick availability check
_GROQ_GENERATE_TIMEOUT = 30   # seconds — generation request


# ============================================================
# Errors
# ============================================================

class GroqUnavailableError(RuntimeError):
    """Raised when the Groq API is unreachable or returns non-2xx on health check."""


class GroqGenerateError(RuntimeError):
    """Raised when the Groq /chat/completions call fails."""


# ============================================================
# GroqAdapter
# ============================================================

class GroqAdapter:
    """
    Thin HTTP adapter for Groq inference.

    Args:
        api_key:  Groq API key. Required for /chat/completions.
                  If None, ``generate()`` raises ``GroqUnavailableError``.
        base_url: Override for the Groq API base (default: GROQ_API_URL).
        timeout:  Request timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = GROQ_API_URL,
        timeout: int = _GROQ_GENERATE_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def check_available(self) -> bool:
        """
        Return True if the Groq API is reachable.

        Uses a lightweight GET on /models (no api_key required for listing).
        Returns False on any error.
        """
        try:
            req = urllib.request.Request(
                f"{self._base_url}/models",
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=_GROQ_CONNECT_TIMEOUT) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        model: str = GROQ_DEFAULT_MODEL,
        max_tokens: int = 1024,
    ) -> str:
        """
        Call Groq /chat/completions and return the assistant message content.

        Raises:
            GroqUnavailableError: if api_key is not configured.
            GroqGenerateError:    if the API call fails or returns an error.
        """
        if not self._api_key:
            raise GroqUnavailableError("Groq API key not configured.")

        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }).encode("utf-8")

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
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as exc:
                    raise GroqGenerateError(f"Unexpected response shape: {data}") from exc
        except urllib.error.HTTPError as exc:
            raise GroqGenerateError(f"Groq HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise GroqUnavailableError(f"Groq unreachable: {exc.reason}") from exc


# ============================================================
# RegexFallback (shared stub — same as ollama_fallback)
# ============================================================

class GroqRegexFallback:
    """Last-resort stub that returns a canned unavailability message."""

    def generate(self, prompt: str) -> str:
        return "[FALLBACK] Service temporarily unavailable. Please try again later."


# ============================================================
# Fallback chain builder
# ============================================================

def build_groq_fallback_chain(
    primary_fn: Callable[[str], str],
    groq_api_key: Optional[str] = None,
    groq_model: str = GROQ_DEFAULT_MODEL,
    groq_base_url: str = GROQ_API_URL,
) -> Callable[[str], str]:
    """
    Build a 3-tier inference chain:

        primary_fn  →  GroqAdapter  →  GroqRegexFallback

    Args:
        primary_fn:    The primary inference function (raises on failure).
        groq_api_key:  Groq API key. Without it Groq tier is skipped.
        groq_model:    Groq model name.
        groq_base_url: Override Groq API URL.

    Returns:
        A callable ``(prompt: str) → str`` that tries each tier in order.
    """
    groq = GroqAdapter(api_key=groq_api_key, base_url=groq_base_url)
    fallback = GroqRegexFallback()

    def chain(prompt: str) -> str:
        # Tier 1: primary
        try:
            return primary_fn(prompt)
        except Exception:
            pass

        # Tier 2: Groq LPU
        try:
            return groq.generate(prompt, model=groq_model)
        except (GroqUnavailableError, GroqGenerateError):
            pass

        # Tier 3: regex fallback
        return fallback.generate(prompt)

    return chain
