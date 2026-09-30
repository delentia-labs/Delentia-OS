"""
The Intent Loop, as the running system (Round 51).

Design (Architect, 2026-10-01): the Intent Loop is self-development from
combining every component of the system in one ordered sequence until a final
result that can really be recorded. Its motto from the first design: the more
it is used, the smarter, faster and cheaper it gets. Its five pillars (Private-OS
whitepaper v7, "Intent Loop Engine") are:

  1 FDIA Gatekeeper      validate the intent: F = D^I x A, security screen
  2 Memory               recall what the user's own data says (and answer warm
                         when a verified answer's evidence is unchanged)
  3 Specialist Executor  do the work with the tools, routed fast or slow
  4 Verifier             check the result against the original intent
  5 Evolution Committer  keep what worked: growth, skill, record

Until now the microservices/intent-loop reference service was the only
"Intent Loop", and its executor and verifier were simulated. In the runtime the
loop already exists as the Constitutional Cycle inside GovernedAutonomousLoop
(GUARD, THINK, ROUTE, ACT, COMPRESS, VERIFY, RECORD, LEARN) plus the 41-algorithm
pipeline. This module names the pillars over what actually ran:

  pillar_report()     one episode, pillar by pillar, from measured values only
  evolution_report()  the motto, measured: for each repeated goal, are later
                      verified runs smaller, faster, cheaper, better informed

Consensus across several models (the original pillar 4's S/4/6/8 tiers) is not
in this process: SignedAI runs as its own service. The report says so.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

PILLARS = ("gatekeeper", "memory", "executor", "verifier", "committer")


def _trace(result: Dict[str, Any], algo_id: str, stage: Optional[str] = None) -> Optional[Dict[str, Any]]:
    for t in (result.get("pipeline") or {}).get("traces", []):
        if t["algo_id"] == algo_id and t["status"] == "ok" and (stage is None or t["stage"] == stage):
            return t
    return None


def _stage_ok(result: Dict[str, Any], stage: str) -> int:
    return sum(1 for t in (result.get("pipeline") or {}).get("traces", []) if t["stage"] == stage and t["status"] == "ok")


def pillar_report(result: Dict[str, Any], loop: Any) -> Dict[str, Any]:
    stopped = result.get("stopped_reason")
    growth = result.get("growth") or {}
    data = growth.get("data") or {}
    verification = result.get("intent_verification") or {}
    steps = result.get("steps") or []
    abv = _trace(result, "ALGO-30")
    fghf = _trace(result, "ALGO-33")
    return {
        "gatekeeper": {
            "guard": (result.get("guard") or {}).get("cord_verdict"),
            "D": data.get("D"), "I": getattr(loop, "_episode_I", None), "data_parts": data.get("parts"),
            "missing_data": data.get("missing"),
            "stopped_here": stopped in ("guard_blocked", "fdia_blocked"),
        },
        "memory": {
            "memories_recalled": len(getattr(loop, "_episode_memory_scores", []) or []),
            "skills_injected": getattr(loop, "_episode_skills_injected", 0),
            "retrieval_algorithms_ok": _stage_ok(result, "recall"),
            "warm_recall": (result.get("warm_recall") or {}).get("hit", False),
            "tool_outputs_compressed": len(getattr(loop, "_episode_compressions", []) or []),
        },
        "executor": {
            "route": (result.get("route") or {}).get("path"),
            "iterations": result.get("iterations"),
            "tool_calls": sum(1 for s in steps if s.get("tool_name")),
            "algorithms_ok": _stage_ok(result, "understand") + _stage_ok(result, "plan") + _stage_ok(result, "act"),
            "cost_usd": (result.get("cost") or {}).get("cost_usd"),
            "model_calls": (result.get("cost") or {}).get("calls"),
        },
        "verifier": {
            "intent_aligned": verification.get("aligned_with_intent") if verification.get("applicable") else None,
            "similarity": verification.get("similarity_score"),
            "belief_confidence": (abv or {}).get("summary", {}).get("confidence"),
            "hallucination_probability": (fghf or {}).get("summary", {}).get("hallucination_probability"),
            "multi_model_consensus": "not in this process (SignedAI runs as a separate service)",
        },
        "committer": {
            "growth_delta": growth.get("delta"), "G": growth.get("G"),
            "verified": bool((growth.get("parts") or {}).get("verified")),
            "skill_extracted": result.get("skill_extracted"),
            "experiment_run": (result.get("experiment") or {}).get("run_id"),
            "audit_algorithms_recorded": (result.get("pipeline") or {}).get("algorithms"),
        },
    }


def _verified(run: Dict[str, Any]) -> bool:
    m = run.get("metrics") or {}
    return bool(m.get("finished") == 1 and m.get("aligned_with_intent") == 1)


def evolution_report(persistence: Any, namespace: str, *, min_runs: int = 2, limit: int = 200) -> Dict[str, Any]:
    """For each goal this namespace has had answered verified at least twice:
    compare the first verified run with the latest."""
    runs = list(reversed(persistence.recent_governed_runs(namespace, limit)))      # oldest first
    by_goal: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        if _verified(run):
            by_goal.setdefault(run["experiment_id"], []).append(run)

    def snapshot(run: Dict[str, Any]) -> Dict[str, Any]:
        m = run["metrics"]
        return {"steps": m.get("iterations"), "seconds": m.get("duration_s"), "cost_usd": m.get("cost_usd"), "D": m.get("data_D"),
                "skills_injected": m.get("skills_injected"), "warm": bool(m.get("warm_recall"))}

    def better(first: Any, last: Any, tolerance: float = 0.0) -> Optional[bool]:
        if first is None or last is None:
            return None
        return bool(last < first - tolerance)

    clusters = []
    for experiment_id, group in by_goal.items():
        if len(group) < min_runs:
            continue
        first, last = snapshot(group[0]), snapshot(group[-1])
        name = experiment_id
        try:
            with persistence._connect() as conn:
                row = conn.execute("SELECT name FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
                name = row[0] if row else experiment_id
        except Exception:
            pass
        clusters.append({
            "goal": name, "verified_runs": len(group), "first": first, "last": last,
            "fewer_steps": better(first["steps"], last["steps"]), "faster": better(first["seconds"], last["seconds"]),
            "cheaper": better(first["cost_usd"], last["cost_usd"]),
            "better_informed": (last["D"] is not None and first["D"] is not None and last["D"] > first["D"]),
        })

    def count(key: str) -> int:
        return sum(1 for c in clusters if c[key])

    n = len(clusters)
    return {
        "namespace": namespace, "goals_repeated": n, "clusters": clusters,
        "summary": {
            "fewer_steps": count("fewer_steps"), "faster": count("faster"), "cheaper": count("cheaper"),
            "better_informed": count("better_informed"),
            "median_D_change": (round(statistics.median(c["last"]["D"] - c["first"]["D"] for c in clusters
                                                        if c["last"]["D"] is not None and c["first"]["D"] is not None), 4)
                                if any(c["last"]["D"] is not None and c["first"]["D"] is not None for c in clusters) else None),
        },
        "note": "Computed only from this namespace's verified, recorded runs of the same goal; 'cheaper' needs runs that report cost.",
    }
