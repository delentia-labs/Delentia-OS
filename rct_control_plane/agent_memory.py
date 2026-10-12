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
        from rct_control_plane import memory_embeddings
        if memory_embeddings.enabled():                  # Round 68 (opt-in): index it by meaning, best effort (a failure is not the memory's failure)
            import asyncio
            try:
                await asyncio.to_thread(memory_embeddings.store_vectors, self._persistence, self.namespace, [{"id": memory_id, "text": content}])
            except Exception:                            # noqa: BLE001
                pass
        return memory_id

    def _ranked(self, query: str, candidates: List[Dict[str, Any]], limit: int) -> List[Any]:
        """(similarity, lexical similarity, candidate) best first. Without embeddings this is exactly the old ranking over the lexical top limit*3; with them every candidate gets
        max(lexical, calibrated embedding similarity), so a paraphrase can win by meaning and a question that shares words still wins by words."""
        from rct_control_plane import memory_embeddings
        cosines = memory_embeddings.similarities(self._persistence, self.namespace, query, candidates) if memory_embeddings.enabled() else None
        if cosines is None:
            matches = self._matcher.match(query, [c["content"] for c in candidates], top_k=limit * 3, threshold=0.0)
            by_text = {c["content"]: c for c in candidates}
            return [(m["score"], m["score"], by_text[m["text"]]) for m in matches if m["text"] in by_text]
        lexical = {m["text"]: m["score"] for m in self._matcher.match(query, [c["content"] for c in candidates], top_k=len(candidates), threshold=0.0)}
        out = []
        for c in candidates:
            lex = lexical.get(c["content"], 0.0)
            cos = cosines.get(c["id"])
            sim = max(lex, memory_embeddings.relevance(cos)) if cos is not None else lex
            out.append((sim, lex, c))
        out.sort(key=lambda t: t[0], reverse=True)
        return out[:max(limit * 3, 1)]

    async def recall_scored(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Like recall(), but each item carries `relevance` (the raw semantic
        similarity to the query, 0..1, not boosted by type or importance) so a
        caller can tell "relevant" from "the least irrelevant thing stored"."""
        candidates = self._persistence.list_memories(namespace=self.namespace)
        from rct_control_plane import memory_eventlog      # Round 66: what the model may be shown (read-time policy; the default keeps every candidate)
        candidates = memory_eventlog.select_for_recall(candidates)
        if not candidates:
            return []
        scored = []
        for similarity_, _lexical, candidate in self._ranked(query, candidates, limit):
            boost = _TYPE_BOOST.get(MemoryType(candidate["memory_type"]), 1.0)
            scored.append((similarity_ * candidate["importance"] * boost, similarity_, candidate))
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

        scored = []
        for similarity_, _lexical, candidate in self._ranked(query, candidates, limit):
            boost = _TYPE_BOOST.get(MemoryType(candidate["memory_type"]), 1.0)
            scored.append((similarity_ * candidate["importance"] * boost, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [c for _, c in scored[:limit]]
        for c in results:
            self._persistence.touch_memory(c["id"])
        return results
