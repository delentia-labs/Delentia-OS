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
from rct_control_plane.semantic_matcher import SemanticMatcher


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
        self._matcher = SemanticMatcher()

    async def store(self, content: str, memory_type: MemoryType,
                     context: Optional[Dict[str, Any]] = None, importance: float = 0.5) -> str:
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        self._persistence.save_memory(
            memory_id=memory_id, namespace=self.namespace, memory_type=memory_type.value,
            content=content, context=context or {}, importance=importance,
        )
        return memory_id

    async def recall(self, query: str, memory_type: Optional[MemoryType] = None, limit: int = 5) -> List[Dict[str, Any]]:
        candidates = self._persistence.list_memories(
            namespace=self.namespace, memory_type=memory_type.value if memory_type else None,
        )
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
