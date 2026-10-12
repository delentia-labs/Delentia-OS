"""
Round 69: two optional uses of a LOCAL language model to make memory recall better at paraphrases. Both are off by default (they need a model) and neither ever sees more than it must:

  DELENTIA_MEMORY_QUESTIONS=ollama        at store time the model writes 3 short questions the memory answers (other words than the memory); they are embedded and kept next to the memory's own vector,
                                          sealed like it (memory_embeddings.store_questions). The questions are never shown to anyone; they only add vectors to match a question against.
  DELENTIA_MEMORY_QUERY_EXPANSION=ollama  at recall time the model rewrites the question 3 ways; the best cosine over the question and its rewrites is used (memory_embeddings.similarities).

Measured on the local qwen2.5:7b (research/recall_lab_r69.py; each held-out set once): hit@3 on 40 English paraphrase questions 37 (embedding alone) -> 38 (questions) -> 39 (both); on the 40 Thai questions of H5
23 -> 26; expansion alone was not better than the embedding on English (35). So the store-time questions carry most of the gain; the expansion is a small extra that costs a model call at every recall.

Safety: the address must be loopback (the same rule as the embedding service; DELENTIA_MEMORY_EMBED_ALLOW_REMOTE=1 lifts it, which then needs the sovereignty policy of the person), the text is clipped, the
output is at most 3 lines of at most 200 characters, a failure or a timeout means no questions (never an error), and a breaker pauses the model for a minute after a failure.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from typing import Dict, List, Optional

LOG = logging.getLogger(__name__)
QUESTIONS_ENV = "DELENTIA_MEMORY_QUESTIONS"
EXPANSION_ENV = "DELENTIA_MEMORY_QUERY_EXPANSION"
MODEL_ENV = "DELENTIA_MEMORY_LLM_MODEL"
DEFAULT_LOCAL_MODEL = "qwen2.5:7b"
TIMEOUT_S = 90.0
BREAKER_S = 60.0
MAX_TEXT_CHARS = 1500
MAX_LINES, MAX_LINE_CHARS = 3, 200
_breaker_until = 0.0
_expansion_cache: Dict[str, List[str]] = {}

QUESTION_PROMPT = ("Below is a note. Write 3 different short questions that this note answers. Use different words than the note (synonyms, other phrasing). "
                   "Output exactly 3 lines, one question per line, no numbering, no extra text.\n\nNote: ")
REWRITE_PROMPT = ("Rewrite the question below in 3 different ways. Use different words (synonyms, other phrasing) but ask for the same thing. "
                  "Output exactly 3 lines, one rewrite per line, no numbering, no extra text.\n\nQuestion: ")


def _on(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("ollama", "1", "on", "true", "yes")


def questions_enabled() -> bool:
    return _on(QUESTIONS_ENV)


def expansion_enabled() -> bool:
    return _on(EXPANSION_ENV)


def reset_breaker() -> None:
    global _breaker_until
    _breaker_until = 0.0
    _expansion_cache.clear()


def model_name() -> str:
    """The local model: DELENTIA_MEMORY_LLM_MODEL, else the model of the `memory` profile when that is an Ollama one, else qwen2.5:7b."""
    explicit = (os.environ.get(MODEL_ENV) or "").strip()
    if explicit:
        return explicit
    try:
        from rct_control_plane.model_config import resolve_model_selection
        selection = resolve_model_selection(profile="memory")
        if selection.provider == "ollama":
            return selection.model
    except Exception:                                                        # noqa: BLE001 - a config problem must not stop memory from working
        pass
    return DEFAULT_LOCAL_MODEL


def _chat(prompt: str) -> Optional[List[str]]:
    """Up to 3 clean lines from the local model, or None (down, slow, refused address, nonsense). Never raises."""
    global _breaker_until
    if time.monotonic() < _breaker_until:
        return None
    from rct_control_plane import memory_embeddings
    url = memory_embeddings.base_url()
    if not memory_embeddings._address_allowed(url):
        LOG.warning("memory model refused: %s is not a loopback address", url)
        return None
    try:
        request = urllib.request.Request(url + "/api/chat", data=json.dumps({"model": model_name(), "messages": [{"role": "user", "content": prompt}], "stream": False, "keep_alive": "30m",
                                                                           "options": {"temperature": 0.2, "num_predict": 120}}).encode("utf-8"), headers={"Content-Type": "application/json"})
        body = json.loads(urllib.request.urlopen(request, timeout=TIMEOUT_S).read())
        raw = str(body["message"]["content"])
    except Exception as exc:                                                 # noqa: BLE001
        _breaker_until = time.monotonic() + BREAKER_S
        LOG.warning("memory model unavailable (%s: %s); recall continues without it for %d s", type(exc).__name__, exc, int(BREAKER_S))
        return None
    lines = [re.sub(r"^[\s\-*\d.)]+", "", ln).strip()[:MAX_LINE_CHARS] for ln in raw.splitlines()]
    return [ln for ln in lines if len(ln) >= 6][:MAX_LINES]


def questions_for(text: str) -> List[str]:
    return _chat(QUESTION_PROMPT + str(text)[:MAX_TEXT_CHARS]) or []


def paraphrases_of(question: str) -> List[str]:
    key = str(question)[:MAX_TEXT_CHARS]
    if key not in _expansion_cache:
        lines = _chat(REWRITE_PROMPT + key)
        if lines is None:
            return []                                                        # not cached: a failure may be temporary
        if len(_expansion_cache) > 256:
            _expansion_cache.clear()
        _expansion_cache[key] = lines
    return _expansion_cache[key]
