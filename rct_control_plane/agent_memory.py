"""
General-purpose cross-session agent memory (Round 22 Phase 9) - ports
the real Memory/MemoryType design and type-boost weighting from
Delentia-Private-OS's personal_agent.py's PersonalAgentMemory, backed
by this kernel's own SQLite persistence (not RCTDB, matching this
kernel's existing real choice) and the ported SemanticMatcher (Task 17)
for real ranking instead of a hand-rolled substring search.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.semantic_matcher import ContentMatcher


class MemoryType(str, Enum):
    CONVERSATION = "conversation"
    PREFERENCE = "preference"
    FACT = "fact"
    EVENT = "event"
    SKILL = "skill"
    GOAL = "goal"


_TYPE_BOOST = {
    MemoryType.GOAL: 2.0, MemoryType.PREFERENCE: 1.8, MemoryType.SKILL: 1.5,
    MemoryType.FACT: 1.3, MemoryType.EVENT: 1.2, MemoryType.CONVERSATION: 1.0,
}


class AgentMemory:
    def __init__(self, namespace: str, persistence: ControlPlanePersistence):
        self.namespace = namespace
        self._persistence = persistence
        self._matcher = ContentMatcher()

    async def store(self, content: str, memory_type: MemoryType,
                     context: Optional[Dict[str, Any]] = None, importance: float = 0.5) -> str:
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        self._persistence.save_memory(
            memory_id=memory_id, namespace=self.namespace, memory_type=memory_type.value,
            content=content, context=context or {}, importance=importance,
        )
        return memory_id

    async def recall_scored(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Like recall(), but each item carries `relevance` (the raw semantic
        similarity to the query, 0..1, not boosted by type or importance) so a
        caller can tell "relevant" from "the least irrelevant thing stored"."""
        candidates = self._persistence.list_memories(namespace=self.namespace)
        from rct_control_plane import memory_eventlog      # Round 66: what the model may be shown (read-time policy; the default keeps every candidate)
        candidates = memory_eventlog.select_for_recall(candidates)
        if not candidates:
            return []
        matches = self._matcher.match(query, [c["content"] for c in candidates], top_k=limit * 3, threshold=0.0)
        by_text = {c["content"]: c for c in candidates}
        scored = []
        for m in matches:
            candidate = by_text.get(m["text"])
            if candidate is None:
                continue
            boost = _TYPE_BOOST.get(MemoryType(candidate["memory_type"]), 1.0)
            scored.append((m["score"] * candidate["importance"] * boost, m["score"], candidate))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _final, similarity, candidate in scored[:limit]:
            self._persistence.touch_memory(candidate["id"])
            results.append({**candidate, "relevance": round(similarity, 4)})
        return results

    async def recall(self, query: str, memory_type: Optional[MemoryType] = None, limit: int = 5) -> List[Dict[str, Any]]:
        candidates = self._persistence.list_memories(
            namespace=self.namespace, memory_type=memory_type.value if memory_type else None,
        )
        from rct_control_plane import memory_eventlog
        candidates = memory_eventlog.select_for_recall(candidates)
        if not candidates:
            return []

        texts = [c["content"] for c in candidates]
        matches = self._matcher.match(query, texts, top_k=limit * 3, threshold=0.0)

        text_to_candidate = {c["content"]: c for c in candidates}
        scored = []
        for m in matches:
            candidate = text_to_candidate.get(m["text"])
            if candidate is None:
                continue
            boost = _TYPE_BOOST.get(MemoryType(candidate["memory_type"]), 1.0)
            final_score = m["score"] * candidate["importance"] * boost
            scored.append((final_score, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [c for _, c in scored[:limit]]
        for c in results:
            self._persistence.touch_memory(c["id"])
        return results
