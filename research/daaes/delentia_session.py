"""
Delentia adapter for the scripted (zero-cost) DAAES cases. (Specification section II: the common AgentAdapter, here for a model that is a fixed program.)

What is REAL in a session: the governed loop built by `agent_factory.build_governed_loop` (the product's only entry point), its gate (`_pre_dispatch_gate`: floor, owner policy, taint, FDIA number), the
approval store and its signatures, the audit chain, the memory event log, the data home on disk. What is SCRIPTED: the model's decisions (a fixed list) and the tool server (an in-memory world that
records every call). Nothing here is Delentia's decision-making by a language model; it is Delentia's runtime around a model that always does what the script says.

The adapter records the shared event taxonomy into a `RunLog` as it goes: decision.proposed / decision.authorized around every gate call, tool.requested / tool.completed around every tool call,
intent events from the goal, checkpoint.committed with the audit-chain head at the end. R2 and R3 replay read those events and nothing else.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from research.daaes.core import digest
from research.daaes.events import NoExternalCalls, RunLog


class _Result:
    def __init__(self, payload: Any) -> None:
        self.content = [type("C", (), {"text": json.dumps(payload, sort_keys=True)})()]


class _Tool:
    def __init__(self, name: str) -> None:
        self.name, self.description, self.input_schema = name, name, {}


class NullKernel:
    """Deterministic stand-in for the algorithm kernel (the loop only calls these two methods); D and I are fixed so a run depends on nothing but its script."""

    def __init__(self, D: float = 1.0, I: float = 1.0) -> None:
        self.D, self.I = D, I

    def synthesize_fdia_inputs(self, intent_text: str) -> Any:
        return self.D, self.I, None

    def algo_04_rct7(self, intent: str) -> List[str]:
        return [f"Step {i} for {intent[:10]}" for i in range(1, 8)]


class ScriptedWorld:
    """The tool server of a session: a dictionary of files. Every call is recorded; writes change `files`."""

    def __init__(self, files: Dict[str, str]) -> None:
        self.files = dict(files)
        self.calls: List[Dict[str, Any]] = []
        self.on_call: Optional[Callable[[str, Dict[str, Any], Any], None]] = None

    async def list_tools(self) -> List[Any]:
        return [_Tool("delentia_read_repo_file"), _Tool("delentia_write_repo_file"), _Tool("delentia_recall")]

    async def call_tool(self, name: str, args: Dict[str, Any]) -> _Result:
        if name == "delentia_read_repo_file":
            out: Dict[str, Any] = {"content": self.files.get(args.get("relative_path", ""), ""), "ok": True}
        elif name == "delentia_write_repo_file":
            self.files[args["relative_path"]] = args["content_text"]
            out = {"ok": True, "bytes": len(args["content_text"])}
        else:
            out = {"ok": True}
        self.calls.append({"tool": name, "args": deepcopy(args), "output": out})
        return _Result(out)

    def state_hash(self) -> str:
        return digest(self.files)


class ReplayWorld:
    """R2's stand-in for the outside: serves recorded outputs in order and refuses everything else (counted, so the test can prove nothing external was called)."""

    def __init__(self, recorded: List[Dict[str, Any]]) -> None:
        self.recorded = deepcopy(recorded)
        self.cursor = 0
        self.calls: List[Dict[str, Any]] = []
        self.external = NoExternalCalls()

    async def list_tools(self) -> List[Any]:
        return [_Tool("delentia_read_repo_file"), _Tool("delentia_write_repo_file"), _Tool("delentia_recall")]

    async def call_tool(self, name: str, args: Dict[str, Any]) -> _Result:
        if self.cursor >= len(self.recorded) or self.recorded[self.cursor]["tool"] != name or digest(self.recorded[self.cursor]["args"]) != digest(args):
            self.external()                                          # not what was recorded: it would have reached the outside world
        item = self.recorded[self.cursor]
        self.cursor += 1
        self.calls.append({"tool": name, "args": deepcopy(args), "output": item["output"]})
        return _Result(item["output"])


@contextlib.contextmanager
def scripted_model(decisions: List[Dict[str, Any]]):
    """Replaces the model's decision function with a fixed list and RESTORES it afterwards (a helper that leaves a global patched breaks every later test)."""
    import rct_control_plane.autonomous_loop as loop_module
    original = loop_module.decide_next_action
    state = {"i": 0}

    async def fake(goal: str, history: Any, available_tools: Any, llm_provider: Any = None, extra_context: str = "") -> Dict[str, Any]:
        i = state["i"]
        state["i"] += 1
        if i < len(decisions):
            d = dict(decisions[i])
            if d.get("final_answer") == "<restate>":
                d["final_answer"] = f"Completed the goal: {goal}"
            return d
        return {"action": "finish", "reasoning": "script exhausted", "final_answer": f"Completed the goal: {goal}", "tool_name": None, "tool_args": {}}
    loop_module.decide_next_action = fake
    try:
        yield state
    finally:
        loop_module.decide_next_action = original


@contextlib.contextmanager
def data_home(home: Path, approver_pub: Optional[str] = None):
    keys = {"DELENTIA_HOME": str(home), "DELENTIA_MEMORY_EMBED": "off", "DELENTIA_MEMORY_KEYS_DIR": str(home / "memkeys"), "DELENTIA_APPROVERS_FILE": str(home / "approvers.json")}
    if approver_pub:
        keys["DELENTIA_APPROVER_PUBKEYS"] = approver_pub
    saved = {k: os.environ.get(k) for k in list(keys) + ["DELENTIA_APPROVER_PUBKEYS"]}
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(keys)
    if not approver_pub:
        os.environ.pop("DELENTIA_APPROVER_PUBKEYS", None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def normalize_steps(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for s in result.get("steps") or []:
        tr = s.get("tool_result") or {}
        out.append({"tool": s.get("tool_name"), "args": s.get("tool_args"), "stopped": s.get("stopped_reason"),
                    "pending": bool(tr.get("pending_approval")), "blocked": bool(tr.get("fdia_blocked")), "output_hash": digest({k: v for k, v in tr.items() if k not in ("approval_policy",)})})
    return out


def run_session(home: Path, goal: str, decisions: List[Dict[str, Any]], world: Any, log: Optional[RunLog] = None, namespace: str = "daaes", approve: bool = False,
                max_iterations: int = 6, intent_id: str = "INT-1") -> Dict[str, Any]:
    """One governed episode (and, with approve=True, the signed approval and the resume of what it paused on). Returns a normalized summary; events go to `log`."""
    from rct_control_plane import approvals
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence

    key = home / "approver.pem"
    pub = approvals.generate_approver_key(str(key)) if not key.exists() else None
    if pub is None:
        pub = json.loads((home / "approver_pub.json").read_text(encoding="utf-8"))["pub"]
    else:
        (home / "approver_pub.json").write_text(json.dumps({"pub": pub}), encoding="utf-8")

    summary: Dict[str, Any] = {"decisions": []}
    with data_home(home, approver_pub=pub), scripted_model(decisions):
        persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
        loop = build_governed_loop(NullKernel(), namespace=namespace, max_iterations=max_iterations, persistence=persistence, mcp_server=world, conversation_turns=0)
        current: Dict[str, Optional[str]] = {"decision": None}
        if log is not None:
            log.emit("intent.created", {"goal": goal}, intent_id=intent_id)

        original_gate = loop._pre_dispatch_gate

        async def gate(g: str, tool: str, args: Dict[str, Any]) -> Any:
            proposed = log.emit("decision.proposed", {"tool": tool, "args": args, "goal": g, "taint": getattr(loop, "_episode_taint", None), "D": loop._episode_D, "I": loop._episode_I}, intent_id=intent_id) if log else None
            out = await original_gate(g, tool, args)
            verdict = "allow" if out is None else ("ask" if out.get("stopped_reason") == "pending_approval" else "block")
            record = {"tool": tool, "args": args, "verdict": verdict, "stopped_reason": (out or {}).get("stopped_reason"), "D": loop._episode_D, "I": loop._episode_I,
                      "taint": getattr(loop, "_episode_taint", None)}
            summary["decisions"].append(record)
            if log:
                authorized = log.emit("decision.authorized", {"verdict": verdict, "stopped_reason": record["stopped_reason"]}, causation_id=proposed["event_id"], intent_id=intent_id)
                current["decision"] = authorized["event_id"]
            return out
        loop._pre_dispatch_gate = gate                                # type: ignore[method-assign]

        real_call = world.call_tool

        async def call(name: str, args: Dict[str, Any]) -> Any:
            requested = log.emit("tool.requested", {"tool": name, "input": args}, causation_id=current["decision"], intent_id=intent_id) if log else None
            try:
                result = await real_call(name, args)
            except Exception as exc:                                  # noqa: BLE001 - a refused external call is recorded, then re-raised to the loop
                if log:
                    log.emit("tool.failed", {"tool": name, "error": type(exc).__name__}, causation_id=requested["event_id"] if requested else None, intent_id=intent_id)
                raise
            out = json.loads(result.content[0].text)
            if log:
                log.emit("tool.completed", {"tool": name, "output": out, "output_hash": digest(out)}, causation_id=requested["event_id"] if requested else None, intent_id=intent_id)
            return result
        world.call_tool = call                                        # type: ignore[method-assign]
        try:
            result = asyncio.run(loop.run(goal))
            summary.update({"stopped_reason": result.get("stopped_reason"), "final_answer": result.get("final_answer"), "steps": normalize_steps(result)})
            if approve and result.get("approval_id"):
                store = loop._pending_actions()
                action = store.get(result["approval_id"])
                signed = approvals.sign_decision(str(key), action.approval_id, action.action_sha256, "APPROVED")
                store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
                if log:
                    log.emit("decision.authorized", {"verdict": "approved_by_human", "approval_digest": action.action_sha256, "tool": action.tool_name}, causation_id=current["decision"], intent_id=intent_id)
                resumed = asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
                summary["resumed"] = {"tool": action.tool_name, "executed_result": digest(resumed.get("executed_result") or {})}
        finally:
            world.call_tool = real_call                               # type: ignore[method-assign]
        with persistence._connect() as conn:
            from rct_control_plane import audit_chain
            report = audit_chain.verify_audit_chain(conn)
            summary["audit"] = {"ok": report.ok, "rows": report.chained_rows, "head": report.head_hash}
        if log:
            log.emit("checkpoint.committed", {"audit_head": summary["audit"]["head"], "audit_rows": summary["audit"]["rows"]}, intent_id=intent_id)
        summary["world_hash"] = world.state_hash() if hasattr(world, "state_hash") else None
    return summary


# ---- the standard scripted episode: two reads, then a write that must wait for a signature, then the signed write
GOAL = "Read docs/a.md and docs/b.md and write the combined summary to docs/summary.md"
DECISIONS = [
    {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "docs/a.md"}, "reasoning": "read a"},
    {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "docs/b.md"}, "reasoning": "read b"},
    {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "docs/summary.md", "content_text": "A and B combined"}, "reasoning": "write"},
]
FILES = {"docs/a.md": "alpha", "docs/b.md": "beta"}
