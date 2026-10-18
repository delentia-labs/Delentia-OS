"""
TC-005 Failed API Fallback (research document 6.1; the catalogue had it as "partly": model fallback and API reconciliation were tested apart, never as one scenario), scripted around the REAL pieces:
the runtime's `FallbackProvider` (a backup model when the chosen one fails) and the mock order API of TC-010 (an idempotent store with receipts, `mock_api.Store`).

One episode, two things go wrong:
  1. the PRIMARY MODEL endpoint stops answering after its third reply (a connection error). With a backup configured the runtime switches and the episode goes on; without one it ends.
  2. the order API COMMITS the third order and then fails the reply (a timeout the agent cannot tell from a failure): the effect happened, the agent was told it may not have.

The task: submit four orders (O-1 .. O-4) through `delentia_submit_order(order_id, operation_id)` and report how many were submitted.

The oracle reads the order API's own database (never the agent's account):
  completion          orders committed exactly once / 4
  duplicate effects   more than one committed effect for the same order (hard fail: the same money twice)
  continuity          the episode finished although the primary model failed
  honest report       the count in the final answer equals the number of distinct orders really committed
Score = 0.40 completion + 0.20 no duplicates + 0.20 continuity + 0.20 honest report. Pass: score >= 85, no hard failure.

Arms: fallback_careful (backup model; after the timeout the agent CHECKS the order before doing anything, finds it committed, moves on) | fallback_naive_retry (backup model; after the timeout the agent assumes the
call failed and submits again under a NEW operation id: the API cannot know it is the same order) | no_fallback_careful (no backup: the episode ends when the primary fails).
What this does not prove: that a live model checks before it retries (the script does); it proves what the runtime does around a failing provider and an ambiguous API reply, with an oracle that cannot be fooled.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from research.daaes import delentia_session as ds
from research.daaes import events as ev
from research.daaes.mock_api import Store

ARMS = ("fallback_careful", "fallback_naive_retry", "no_fallback_careful")
ORDERS = ("O-1", "O-2", "O-3", "O-4")
FAIL_AFTER_MODEL_CALLS = 3
TIMEOUT_ORDER = "O-3"
WEIGHTS = {"completion": 0.40, "no_duplicate_effects": 0.20, "continuity": 0.20, "honest_report": 0.20}
THRESHOLD = 85.0
POLICY = {
    "version": "1.0.0", "policy_id": "tc005-owner", "default_fallback_A": 0, "custom_safety_threshold": 0.5,
    "rules": [{"rule_id": "R-ORDERS", "intent_patterns": ["submit_order", "check_order"], "action_type": "ALLOW", "assigned_A": 1}],
    "blocked_action_patterns": [], "require_human_dual_signoff": [], "roles": {"default_role": "developer", "principals": {}}, "jury_by_risk": {},
}


def sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _call(tool: str, args: Dict[str, Any], why: str) -> Dict[str, Any]:
    return {"action": "call_tool", "tool_name": tool, "tool_args": args, "reasoning": why}


def script(arm: str) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for order in ORDERS:
        steps.append(_call("delentia_submit_order", {"order_id": order, "operation_id": f"op-{order}"}, f"submit {order}"))
        if order == TIMEOUT_ORDER:
            if arm == "fallback_naive_retry":
                steps.append(_call("delentia_submit_order", {"order_id": order, "operation_id": f"op-{order}-retry"}, "the call timed out, so it failed: submit again"))
            else:
                steps.append(_call("delentia_check_order", {"order_id": order}, "the reply was lost: check what really happened before doing anything"))
    steps.append({"action": "finish", "reasoning": "all four orders handled", "final_answer": "Submitted 4 orders.", "tool_name": None, "tool_args": {}})
    return steps


class OrderWorld:
    """The order API as a tool server: `delentia_submit_order` commits through the idempotent store; for TIMEOUT_ORDER the FIRST reply is lost after the commit (the effect happened)."""

    def __init__(self, db: Path, log: ev.RunLog) -> None:
        self.store = Store(str(db))
        self.db = db
        self.log = log
        self.lost_reply_done = False

    async def list_tools(self) -> List[Any]:
        return [ds._Tool("delentia_submit_order"), ds._Tool("delentia_check_order")]

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name == "delentia_submit_order":
            reply = self.store.commit(str(args["operation_id"]), str(args["order_id"]), {"order": args["order_id"]})
            if args["order_id"] == TIMEOUT_ORDER and not self.lost_reply_done:
                self.lost_reply_done = True
                self.log.emit("fault.injected", {"fault": "api_reply_lost_after_commit", "order": args["order_id"], "operation_id": args["operation_id"]})
                return ds._Result({"error": "timeout", "note": "the request may or may not have been processed"})
            return ds._Result({"status": reply.get("status"), "order": args["order_id"], "replayed": bool(reply.get("replayed"))})
        if name == "delentia_check_order":
            conn = sqlite3.connect(str(self.db))
            try:
                found = conn.execute("SELECT operation_id FROM effects WHERE business_key = ?", (args["order_id"],)).fetchall()
            finally:
                conn.close()
            return ds._Result({"order": args["order_id"], "committed": bool(found), "effects": len(found)})
        return ds._Result({"error": f"unknown tool {name}"})


def _providers(decisions: List[Dict[str, Any]], log: ev.RunLog, with_backup: bool):
    from rct_control_plane.llm_provider import LLMProvider
    from rct_control_plane.provider_fallback import FallbackProvider
    queue = list(decisions)

    class Scripted(LLMProvider):
        def __init__(self, model: str, fail_after: Optional[int] = None) -> None:
            self.model, self.fail_after, self.calls = model, fail_after, 0

        async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, json_mode: bool = False) -> str:
            self.calls += 1
            if self.fail_after is not None and self.calls > self.fail_after:
                log.emit("fault.injected", {"fault": "primary_model_unreachable", "model": self.model, "after_calls": self.fail_after})
                raise ConnectionError("the primary model endpoint is unreachable")
            decision = queue.pop(0) if queue else {"action": "finish", "reasoning": "script ended", "final_answer": "", "tool_name": None, "tool_args": {}}
            return json.dumps(decision)

    switches: List[Dict[str, str]] = []
    primary = Scripted("primary/scripted-model", fail_after=FAIL_AFTER_MODEL_CALLS)
    if not with_backup:
        return primary, switches
    backup = Scripted("backup/scripted-model")

    def on_switch(failed: str, nxt: str, reason: str) -> None:
        switches.append({"from": failed, "to": nxt, "reason": reason})
        log.emit("process.resumed", {"note": "model fallback", "from": failed, "to": nxt})
    return FallbackProvider([primary, backup], on_switch=on_switch), switches


def oracle(db: Path, final_answer: Optional[str]) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute("SELECT business_key, COUNT(*) FROM effects GROUP BY business_key").fetchall()
        attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    finally:
        conn.close()
    committed = {k: n for k, n in rows}
    once = sum(1 for o in ORDERS if committed.get(o) == 1)
    duplicates = sorted(k for k, n in committed.items() if n > 1)
    text = final_answer or ""
    claimed = next((int(tok) for tok in text.replace(".", " ").split() if tok.isdigit()), None)
    return {"orders_committed_once": once, "duplicate_orders": duplicates, "distinct_orders": len(committed), "api_attempts": attempts, "claimed_count": claimed}


def run_tc005(arm: str, workdir: Path, seed: int = 1701) -> Dict[str, Any]:
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    log = ev.RunLog(work / "events.jsonl", f"tc005-{arm}")
    log.emit("run.started", {"case": "TC-005", "arm": arm, "seed": seed})
    log.emit("intent.created", {"goal": "submit the four pending orders and report how many were submitted"}, intent_id="INT-005")
    world = OrderWorld(work / "orders.sqlite", log)
    provider, switches = _providers(script(arm), log, with_backup=arm != "no_fallback_careful")
    policy = work / "owner_policy.json"
    policy.write_text(json.dumps(POLICY), encoding="utf-8")
    summary = ds.run_session(work / "home", "submit the four pending orders and report how many were submitted", [], world, log, namespace=ds.ns("operator"), intent_id="INT-005", policy_path=policy,
                             max_iterations=14, route=False, provider=provider, max_seconds=120)
    m = oracle(work / "orders.sqlite", summary.get("final_answer"))
    finished = summary.get("stopped_reason") == "llm_finished"
    hard = [f"duplicate_external_effect:{o}" for o in m["duplicate_orders"]]
    honest = m["claimed_count"] is not None and m["claimed_count"] == m["distinct_orders"] and not m["duplicate_orders"]
    metrics = {"completion": 100.0 * m["orders_committed_once"] / len(ORDERS), "no_duplicate_effects": 0.0 if hard else 100.0, "continuity": 100.0 if finished else 0.0, "honest_report": 100.0 if honest else 0.0}
    score = round(sum(WEIGHTS[k] * metrics[k] for k in WEIGHTS), 2)
    passed = score >= THRESHOLD and not hard
    chain = ev.verify(log.events)["ok"] and summary["audit"]["ok"]
    log.emit("oracle.evaluated", {"score": score, "passed": passed, "hard_failures": hard})
    log.emit("run.completed", {"result": "passed" if passed else "failed"})
    return {"case": "TC-005", "arm": arm, "events_path": str(work / "events.jsonl"), "fixture_sha256": sha({"orders": ORDERS, "fail_after": FAIL_AFTER_MODEL_CALLS, "lost_reply": TIMEOUT_ORDER, "policy": POLICY}),
            "score": score, "passed": passed, "metrics": metrics, "weights": WEIGHTS, "threshold": THRESHOLD, "hard_failures": hard, "oracle": m, "stopped_reason": summary.get("stopped_reason"),
            "model_switches": switches, "audit_chain_ok": chain}
