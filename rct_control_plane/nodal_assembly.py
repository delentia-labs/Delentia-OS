"""
Nodal Assembly (Round 21 Phase 3) — real parallel dispatch of an
EXPLICIT list of algorithm/tool nodes, merged via ALGO-32 MCTR's
already-real ChainMerger/AnswerSynthesizer.

Scoped deliberately (confirmed with the user 2026-09-18): this module
does NOT attempt to auto-detect "independent sub-goals" from natural-
language intent text - that would be an unvalidated heuristic. Callers
supply the real node list explicitly (their own routing logic, or a
future, separately-validated sub-goal detector, decides WHAT to
assemble; this module only handles the real HOW: dispatch concurrently,
merge honestly).
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Tuple

from rct_control_plane.algo_32_mctr import (
    ThoughtChain, ReasoningStep, ReasoningStrategy, ChainStatus,
    ChainMerger, AnswerSynthesizer, MergeStrategy, SynthesizedAnswer,
)


def wrap_as_thought_chain(node_id: str, query: str, result: Any, confidence: float = 0.8) -> ThoughtChain:
    """Wraps one real node's real result as a real single-step
    ThoughtChain, so it can flow through MCTR's real, tested merge/
    synthesis code without fabricating multi-step reasoning that never
    happened."""
    if isinstance(result, dict):
        evidence = [f"{k}={v!r}"[:200] for k, v in list(result.items())[:5]]
        reasoning = f"Real output from {node_id}: {result!r}"[:2000]
    else:
        evidence = [repr(result)[:200]]
        reasoning = f"Real output from {node_id}: {result!r}"[:2000]

    step = ReasoningStep(
        step_id=f"{node_id}-step1", step_number=1,
        description=f"Real execution of node '{node_id}'",
        reasoning=reasoning, conclusion=reasoning[:300], evidence=evidence,
        confidence=confidence, dependencies=[],
    )
    now = datetime.now(timezone.utc)
    return ThoughtChain(
        chain_id=f"assembly-{node_id}-{uuid.uuid4().hex[:8]}",
        query=query, strategy=ReasoningStrategy.FORWARD_CHAINING, steps=[step],
        conclusion=step.conclusion, confidence=confidence, status=ChainStatus.COMPLETED,
        created_at=now, completed_at=now, execution_time=0.0,
        metadata={"node_id": node_id}, simulated=False,
    )


async def assemble(
    query: str,
    nodes: List[Tuple[str, Callable, tuple, dict]],
    merger: ChainMerger,
    synthesizer: AnswerSynthesizer,
    strategy: MergeStrategy = MergeStrategy.HYBRID,
) -> SynthesizedAnswer:
    """Real concurrent dispatch of an explicit node list ("Nodal
    Assembly" - nodes assemble for this one call, then dissolve; no
    persistent multi-agent state is kept here). Each node's REAL result
    is wrapped as a real ThoughtChain and merged via already-real MCTR
    code."""

    async def _run_one(node_id: str, fn: Callable, args: tuple, kwargs: dict) -> ThoughtChain:
        if inspect.iscoroutinefunction(fn):
            result = await fn(*args, **kwargs)
        else:
            result = fn(*args, **kwargs)
        return wrap_as_thought_chain(node_id, query, result)

    chains = list(await asyncio.gather(*[_run_one(nid, fn, args, kwargs) for nid, fn, args, kwargs in nodes]))

    merged = await merger.merge_chains(chains, strategy=strategy)
    return await synthesizer.synthesize_answer(chains, merged_chain=merged, conflicts_resolved=0)
