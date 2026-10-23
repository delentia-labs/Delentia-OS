"""
Round 83, T14: what an episode that did not finish has already DONE.

A person who finds a stopped episode (a signature is awaited, the gate refused a call, a tool raised, the process was cut off) needs three facts before touching it again: which side effects
already happened, which one is waiting, and whether running the goal again could repeat a side effect. This reads only the episode's own steps; it asks no model and changes nothing.

Classes (from the loop's own sets, so they cannot drift from what the gate enforces):
  side effect   a tool the loop gates as dangerous or that always needs a signature (writes, commands, schedules, delegation, egress)
  read only     everything else
A step has one outcome:
  ran           the tool ran and returned no error
  waiting       the gate parked it for a signature (nothing happened yet)
  refused       the gate refused it (nothing happened)
  error         the tool raised: for a SIDE-EFFECT tool this is "outcome unknown" (the effect may have happened before the error), never "did not happen"
Rerunning the goal is `safe` only when no side effect ran and none is of unknown outcome.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _side_effect_tools() -> frozenset:
    from rct_control_plane import governed_autonomous_loop as g
    return frozenset(g.TAINT_GATED_TOOLS | g.TAINT_EGRESS_TOOLS | g._ALWAYS_NEEDS_APPROVAL_TOOLS | g.RISKY_TOOLS)


def _outcome(result: Any) -> str:
    if not isinstance(result, dict):
        return "ran"
    if result.get("pending_approval"):
        return "waiting"
    if result.get("fdia_blocked") or result.get("blocked"):
        return "refused"
    if result.get("error"):
        return "error"
    return "ran"


def partial_completion(result: Dict[str, Any]) -> Dict[str, Any]:
    side_effects = _side_effect_tools()
    ran_side: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []
    waiting: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    read_only = 0
    errored_read = 0
    for step in result.get("steps") or []:
        tool = step.get("tool_name")
        if not tool:
            continue
        outcome = _outcome(step.get("tool_result"))
        item = {"iteration": step.get("iteration"), "tool": tool}
        if outcome == "waiting":
            waiting.append({**item, "approval_id": (step.get("tool_result") or {}).get("approval_id") or result.get("approval_id")})
        elif outcome == "refused":
            refused.append(item)
        elif tool in side_effects:
            (ran_side if outcome == "ran" else unknown).append(item)
        elif outcome == "ran":
            read_only += 1
        else:
            errored_read += 1
    stopped = result.get("stopped_reason")
    finished = bool(result.get("final_answer")) and not waiting and not refused and not unknown and stopped not in {"waiting_for_clarification", "plan_ready"}
    safe = not ran_side and not unknown
    parts = []
    if finished:
        parts.append("The episode finished.")
    else:
        parts.append(f"The episode stopped early ({stopped}).")
    parts.append(f"{read_only} read-only step(s) ran" + (f", {errored_read} failed" if errored_read else "") + ".")
    if ran_side:
        parts.append("Side effects that DID happen: " + ", ".join(f"{s['tool']} (step {s['iteration']})" for s in ran_side) + ".")
    if unknown:
        parts.append("Outcome UNKNOWN (the tool raised an error, the effect may have happened): " + ", ".join(f"{s['tool']} (step {s['iteration']})" for s in unknown) + ".")
    if waiting:
        parts.append("Waiting for a signature (nothing has happened yet): " + ", ".join(f"{s['tool']} (step {s['iteration']})" for s in waiting) + ".")
    if refused:
        parts.append("Refused by the gate (nothing happened): " + ", ".join(f"{s['tool']} (step {s['iteration']})" for s in refused) + ".")
    parts.append("Running the same goal again " + ("cannot repeat a side effect." if safe else "could repeat the side effects listed above: check them first."))
    return {"finished": finished, "stopped_reason": stopped, "read_only_ran": read_only, "read_only_failed": errored_read, "side_effects_ran": ran_side, "outcome_unknown": unknown,
            "waiting_for_signature": waiting, "refused": refused, "safe_to_rerun": safe, "summary": " ".join(parts)}
