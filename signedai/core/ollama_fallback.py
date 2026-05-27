"""
OllamaFallback — Local SLM Adapter for RCT HexaCore Architecture

Provides a zero-cost local inference fallback via the Ollama runtime.
When cloud API models are unavailable (network outage, rate-limit, air-gap),
the fallback chain attempts:

    1. Primary cloud model (OpenRouter)
    2. OllamaFallback  — local LLM via Ollama REST API
    3. RegexFallback   — deterministic pattern-matching stub

OLLAMA_DEFAULT_MODEL = "llama3.1:8b"
OLLAMA_API_URL       = "http://localhost:11434"
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

OLLAMA_DEFAULT_MODEL = "llama3.1:8b"
OLLAMA_API_URL = "http://localhost:11434"
OLLAMA_TIMEOUT_SECONDS = 30
OLLAMA_FALLBACK_VERSION = "1.0"


# ============================================================
# OllamaFallback
# ============================================================

class OllamaFallback:
    """
    Thin HTTP client for the Ollama local inference runtime.

    Communicates with Ollama's REST API (POST /api/generate).
    Designed to be fully mockable in tests — all HTTP is done via
    ``urllib.request.urlopen`` (no third-party HTTP library required).

    Args:
        base_url: Base URL of the Ollama server (default: http://localhost:11434)
        timeout: HTTP timeout in seconds
    """

    def __init__(
        self,
        base_url: str = OLLAMA_API_URL,
        timeout: int = OLLAMA_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_available(self) -> bool:
        """
        Return True if the Ollama server is reachable (GET /api/tags succeeds).
        Never raises — returns False on any error.
        """
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        model: str = OLLAMA_DEFAULT_MODEL,
        stream: bool = False,
    ) -> str:
        """
        Run a single-shot inference request.

        Args:
            prompt: The prompt text to send
            model:  Ollama model tag (default: llama3.1:8b)
            stream: Whether to request streaming (default: False)

        Returns:
            The model response text

        Raises:
            OllamaUnavailableError: if the server cannot be reached
            OllamaGenerateError: if the server returns a non-2xx status
        """
        body = json.dumps(
            {"model": model, "prompt": prompt, "stream": stream}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status not in (200, 201):
                    raise OllamaGenerateError(
                        f"Ollama returned HTTP {resp.status}"
                    )
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "")
        except urllib.error.URLError as exc:
            raise OllamaUnavailableError(
                f"Ollama server not reachable at {self.base_url}: {exc}"
            ) from exc
        except OllamaGenerateError:
            raise
        except Exception as exc:
            raise OllamaGenerateError(f"Ollama generate failed: {exc}") from exc


# ============================================================
# Errors
# ============================================================

class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama server is not reachable."""


class OllamaGenerateError(RuntimeError):
    """Raised when Ollama returns an error response."""


# ============================================================
# RegexFallback
# ============================================================

class RegexFallback:
    """
    Deterministic last-resort fallback.  Returns a canned response when
    both cloud API and Ollama are unavailable.

    Useful in testing and air-gapped CI environments.
    """

    def generate(self, prompt: str, **_kwargs: Any) -> str:  # noqa: ARG002
        return (
            "[FALLBACK] Service temporarily unavailable. "
            "Please retry or contact support."
        )


# ============================================================
# Fallback chain
# ============================================================

def build_fallback_chain(
    primary_fn: Optional[Callable[[str], str]] = None,
    ollama_model: str = OLLAMA_DEFAULT_MODEL,
    ollama_base_url: str = OLLAMA_API_URL,
) -> Callable[[str], str]:
    """
    Build a three-tier inference fallback chain:

        1. ``primary_fn``   — caller-supplied cloud API function (may be None)
        2. ``OllamaFallback`` — local LLM via Ollama
        3. ``RegexFallback``  — static stub (always succeeds)

    Returns:
        A callable ``(prompt: str) -> str`` that tries each tier in order.
    """
    ollama = OllamaFallback(base_url=ollama_base_url)
    regex_fb = RegexFallback()

    def chain(prompt: str) -> str:
        # Tier 1 — primary cloud model
        if primary_fn is not None:
            try:
                result = primary_fn(prompt)
                if result:
                    return result
            except Exception:
                pass

        # Tier 2 — local Ollama
        if ollama.check_available():
            try:
                return ollama.generate(prompt, model=ollama_model)
            except Exception:
                pass

        # Tier 3 — deterministic stub
        return regex_fb.generate(prompt)

    return chain
