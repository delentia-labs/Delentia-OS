"""
RCTDBFacade (Round 23 Phase 11 Task 25) — unifies the 5 conceptual
RCTDB collections the Architect's own whitepaper defines
(whitepapers/01_foundation/chapters/Chapter03_Vault1068_and_RCTDB_full.md:
experiments, experiment_runs, deltas, mem_profiles, architect_decisions)
under one real, correctly-named object.

This is a THIN composition wrapper - it reuses existing, already-real
objects (ControlPlanePersistence, DeltaEngine, AgentMemory) rather than
reimplementing storage or logic. It does NOT replace RCTDBClient
(algo_10_delta_memory.py), which is real, used code for a genuinely
different thing: Vault-1068's document/manifest store, not RCTDB's
runtime experience records - both stay, per Zero-Delete.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from rct_control_plane.agent_memory import AgentMemory
    from rct_control_plane.algo_25_delta_block import DeltaEngine
    from rct_control_plane.persistence import ControlPlanePersistence


class RCTDBFacade:
    def __init__(self, persistence: "ControlPlanePersistence", delta_engine: "DeltaEngine", agent_memory: "AgentMemory"):
        self._persistence = persistence
        self._delta_engine = delta_engine
        self._agent_memory = agent_memory

    def get_deltas_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._delta_engine.get_session_deltas(session_id)]

    async def get_relevant_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return await self._agent_memory.recall(query, limit=limit)

    def get_architect_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._persistence.list_architect_decisions(limit=limit)

    def compare_experiment(self, experiment_id: str) -> Dict[str, Any]:
        return self._persistence.compare_experiment_runs(experiment_id)

    def restore_session_context(self, session_id: str) -> Dict[str, Any]:
        """Real composite query matching the whitepaper's own example:
        "restore all M and R entries ... to reconstruct the decision
        context." Real deltas + real reconstructed state, no fabricated
        aggregation."""
        deltas = self.get_deltas_for_session(session_id)
        state = self._delta_engine.reconstruct_state(session_id)
        return {
            "session_id": session_id,
            "deltas": deltas,
            "delta_count": len(deltas),
            "reconstructed_state": state.current_data,
            "last_updated": state.last_updated,
        }
