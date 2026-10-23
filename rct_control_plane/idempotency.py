"""
Round 91: idempotency keys for tool calls, so that continuing a crashed episode cannot do a side effect twice at a service that honours them.

The problem (DAAES TC-010, Round 84): a tool call that was about to run, or was running, when the process stopped has an UNKNOWN outcome. The journal refuses to run such a step again on its own,
and a person may still decide "go on". If the call is simply repeated, a service that did receive the first one performs it a second time (two payments, two e-mails, two tickets).

The standard answer is a key the SERVICE can use to recognise a repeat. A call gets a key that depends only on what the call is, not on which process makes it:

    key = "dl-" + first 32 hex of SHA-256( root episode | tool | SHA-256(arguments) | n )

where `root episode` is the first episode of a chain of resumes, and `n` counts earlier calls of the same tool with the same arguments in that chain (two DELIBERATE identical calls get
different keys; the retry of one interrupted call gets the same key as the call it retries, because the journal remembers the key of the dangling step and hands it to the resumed episode's first
identical call). The key travels as the MCP request meta `delentia/idempotency-key` to external servers for tools that can change something, and the OpenAPI bridge sends it as the HTTP header
`Idempotency-Key` on POST, PUT, PATCH and DELETE.

What this does NOT do: a service that ignores the header still performs the call twice, so the resume note says so; the local tools (file writes, shell) do not use keys, and for them the journal's
"outcome unknown: check first" rule is the protection. A key is not a secret and not a permission.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
from typing import Any, Dict, Optional

ENV = "DELENTIA_IDEMPOTENCY"
META_KEY = "delentia/idempotency-key"
HEADER = "Idempotency-Key"
KEY_PREFIX = "dl-"

# Set by the governed loop just before it dispatches a call that can change something; read by the code that talks to an external service.
current_key: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("delentia_idempotency_key", default=None)


def enabled() -> bool:
    return (os.environ.get(ENV) or "on").strip().lower() not in ("off", "0", "false", "no")


def args_sha(args: Any) -> str:
    """The same canonical digest the journal uses for arguments, so a step read back from the journal hashes the same as the call that wrote it."""
    return hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def key_for(root_episode: str, tool: str, arguments_sha256: str, nth: int) -> str:
    material = f"{root_episode}|{tool}|{arguments_sha256}|{int(nth)}"
    return KEY_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def valid(key: Any) -> bool:
    return isinstance(key, str) and key.startswith(KEY_PREFIX) and 16 <= len(key) <= 80 and all(c in "0123456789abcdef" for c in key[len(KEY_PREFIX):])


class KeyIssuer:
    """One per episode. Hands out the key for each call that is about to run: the key of the interrupted call it retries, or a fresh one counted from where the chain left off."""

    def __init__(self, root_episode: str, base_counts: Optional[Dict[str, int]] = None, inherited: Optional[Dict[str, str]] = None):
        self.root = root_episode
        self.counts: Dict[str, int] = dict(base_counts or {})
        self.inherited: Dict[str, str] = dict(inherited or {})

    def issue(self, tool: str, arguments: Any) -> str:
        sha = args_sha(arguments)
        slot = f"{tool}|{sha}"
        retry = self.inherited.pop(slot, None)
        if retry is not None:
            return retry
        n = self.counts.get(slot, 0)
        self.counts[slot] = n + 1
        return key_for(self.root, tool, sha, n)

    def snapshot(self) -> Dict[str, int]:
        return dict(self.counts)
