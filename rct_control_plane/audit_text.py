"""
Round 68: personal text must not sit in the hash chain in the clear.

Found while extending erasure to the other tables (Round 68): the audit trail is hash-chained, so a row cannot be edited or removed - and `governed_loop_episode_start` stored the person's whole GOAL, and
every `autonomous_loop_step` row stored the model's reasoning and the tool arguments, as plain text. Erasing a person's memory (Round 67) therefore left what they asked, word for word, in the chain.

The CLAUDE.md rule is "the chain holds only hashes; the readable copy depends on a key". This module applies it to the fields of an audit row that carry a person's words:
  * writing:  `protect(namespace, changes, fields)` replaces each named field by {"sealed": <AES-GCM text under the person's key>, "sha256": ..., "chars": n}; the row's hash covers the ciphertext,
              so the chain keeps verifying after the key is destroyed;
  * reading:  `reveal(namespace, value)` gives the text back to anyone who still holds the key, and "[erased]" once it is destroyed; a value that was never sealed is returned as it is.
`DELENTIA_AUDIT_TEXT=plain` writes the old plain rows (kept for hosts that read the raw table); the default is sealed. Sealing uses the same per-person key as the memory log (`memory_erasure.py`), so one
key destruction erases both.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable

MODE_ENV = "DELENTIA_AUDIT_TEXT"
ERASED = "[erased]"


def sealing_on() -> bool:
    from rct_control_plane import memory_erasure
    return (os.environ.get(MODE_ENV) or "sealed").strip().lower() not in ("plain", "off", "0", "false", "no") and memory_erasure.sealing_enabled()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def protect(namespace: str, changes: Dict[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    """A copy of `changes` with the named fields sealed (when sealing is on and there is something in the field)."""
    if not sealing_on():
        return changes
    from rct_control_plane import memory_erasure
    out = dict(changes)
    for name in fields:
        value = out.get(name)
        if value in (None, "", [], {}):
            continue
        sealed = memory_erasure.seal(namespace, json.dumps({"v": value}, ensure_ascii=False, default=str))
        if not memory_erasure.is_sealed(sealed):                         # no key could be made: the field stays as it was rather than fail an audit write
            continue
        out[name] = {"sealed": sealed, "sha256": _digest(value), "chars": len(json.dumps(value, ensure_ascii=False, default=str))}
    return out


def is_sealed_value(value: Any) -> bool:
    return isinstance(value, dict) and set(value) >= {"sealed", "sha256"}


def reveal(namespace: str, value: Any) -> Any:
    """The text of a field as `protect` wrote it, "[erased]" when the person's key is gone, the value itself when it was never sealed."""
    if not is_sealed_value(value):
        return value
    from rct_control_plane import memory_erasure
    opened = memory_erasure.open_payload(namespace, value["sealed"])
    if opened.get("_erased"):
        return ERASED
    return opened.get("v")


def reveal_changes(namespace: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    """`changes` with every sealed field opened (for the Desk and the governance view)."""
    return {k: reveal(namespace, v) for k, v in changes.items()} if isinstance(changes, dict) else changes


def experiment_label(goal: str) -> str:
    """The name an RCTDB experiment gets. An experiment is shared by everyone who asked the same goal, so it has no one key to seal under: with sealing on it is named by a hash of the goal (the id already is one)."""
    if sealing_on():
        return "goal sha256:" + hashlib.sha256(str(goal).encode("utf-8")).hexdigest()[:16]
    return str(goal)[:200]
