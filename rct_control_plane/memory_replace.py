"""
Round 72: when a fact changes, the person says so (`replaces`), and the old value stops being offered.

Recall finds what resembles the question. Two memories about the same thing - "the staging database is stg-db-1" and, months later, "the staging database
moved to stg-db-2" - both resemble it, and nothing in the text says which is current. Round 69 tried to guess from marker words ("now", "moved", "no longer"):
+2 of 20 against the +5 it had to gain, so it was not adopted. This is the other way: the PERSON (or the owner) names the memory a new one replaces.

  * `replace(old, new text)` stores the new memory with `context.replaces = old id`, revokes the old one with the reason "superseded by <new id>" (soft: the row and
    its history stay, time travel still shows it, the audit chain records both steps) and, when the old memory was a pinned rule, pins the new one in its place;
  * it is a person's act, like pinning: there is no model tool for it, and a memory stored after outside text was read cannot replace anything - otherwise a web page
    could make the agent "update" the host of the database into its own;
  * `likely_replaced(...)` is only a HINT shown to the person who is about to store a memory ("this looks like it replaces mem_x: ..."): it never changes anything.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

HINT_THRESHOLD = 0.40                       # lexical similarity (ContentMatcher, 0..1) a stored memory needs to be offered as "this may be replaced"; see research/replaces_r72.py
MARKERS = re.compile(r"\b(now|changed|change|moved|switched|instead|no longer|renamed|replaced|replacing|extended|raised|from now on|updated|has been|is now|new)\b|ตอนนี้|เปลี่ยนเป็น|ย้ายไป|แทน|ใหม่", re.IGNORECASE)


class ReplaceError(ValueError):
    """The replacement was refused; the message says why in words a person can act on."""


def announces_a_change(text: str) -> bool:
    return bool(MARKERS.search(str(text or "")))


def likely_replaced(persistence: Any, namespace: str, text: str, limit: int = 3, threshold: float = HINT_THRESHOLD) -> List[Dict[str, Any]]:
    """Live memories of this person that `text` may replace, most likely first: [{id, content, score, change_announced}]. A hint, never an action."""
    from rct_control_plane.semantic_matcher import ContentMatcher
    live = persistence.list_memories(namespace)
    if not live or not str(text or "").strip():
        return []
    by_text = {m["content"]: m for m in live}
    announced = announces_a_change(text)
    found = ContentMatcher().match(text, list(by_text), top_k=max(limit * 3, 5), threshold=0.0)
    out = []
    for item in found:
        if item["score"] < threshold or item["text"] == text:
            continue
        m = by_text[item["text"]]
        out.append({"id": m["id"], "content": m["content"][:160], "score": round(float(item["score"]), 3), "change_announced": announced})
    return out[:limit]


async def replace(memory: Any, old_id: str, content: str, *, by: str = "", memory_type: Any = None, importance: Any = None, allow_tainted: bool = False,
                  context: Any = None) -> Dict[str, Any]:
    """Store `content` as the current version of memory `old_id` and retire the old one. `memory` is an AgentMemory. Raises ReplaceError when it cannot be done;
    nothing is stored in that case."""
    from rct_control_plane.agent_memory import MemoryType
    persistence, namespace = memory._persistence, memory.namespace
    content = str(content or "").strip()
    if not content:
        raise ReplaceError("the new text is empty")
    old = next((m for m in persistence.list_memories(namespace) if m["id"] == old_id), None)
    if old is None:
        raise ReplaceError(f"no live memory {old_id!r} in this namespace (it may already be revoked or replaced)")
    ctx = dict(context or {})
    if isinstance(ctx.get("provenance"), dict) and ctx["provenance"].get("tainted") and not allow_tainted:
        raise ReplaceError("this text was written after text from outside was read; it cannot replace a memory until a person has reviewed it")
    kind = memory_type if isinstance(memory_type, MemoryType) else MemoryType(str(memory_type or old["memory_type"]))
    weight = float(old["importance"] if importance is None else importance)
    ctx.update({"replaces": old_id, "replaces_by": (by or "")[:80]})
    new_id = await memory.store(content, kind, context=ctx, importance=weight)
    persistence.revoke_memory(old_id, namespace, f"superseded by {new_id}")
    pinned = None
    if old.get("pinned_at"):
        pinned = persistence.pin_memory(new_id, namespace, True, by=by or "replace", allow_tainted=allow_tainted)
    try:
        persistence.append_audit(entity_type="memory_replaced", entity_id=new_id, action="replaced", actor=(by or namespace)[:80],
                                 changes={"namespace": namespace, "old_id": old_id, "new_id": new_id, "pin_moved": bool(pinned and pinned.get("ok"))})
    except Exception:                                               # noqa: BLE001 - the replacement itself is stored
        pass
    return {"old_id": old_id, "new_id": new_id, "pin_moved": bool(pinned and pinned.get("ok")), "pin_note": (pinned or {}).get("reason") if pinned and not pinned.get("ok") else None}
