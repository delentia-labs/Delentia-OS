"""
The agent process of TC-010: a 12-stage order workflow run as its own OS process so that it can be killed for real (TerminateProcess / SIGKILL) and started again.

    python -m research.daaes.workflow_child --dir <agent_dir> --api <port> --mode reference|naive_new_key|delentia --run <run_id>

Stages: 1 read orders, 2 validate, 3 de-duplicate, 4 totals, 5 approval list, 6 save draft, 7 send each order to the mock API, 8 record each receipt, 9 update each order's status,
10 verify against the API, 11 report, 12 close. Stages 7-9 are the critical section: the API can commit while the agent has not yet written down that it did.

Kill points are hooks that write a marker file and then WAIT, so the supervisor can terminate the process at exactly that line, with no chance to clean up (the process is blocked in a sleep when it
is killed). They are armed by DAAES_KILL_POINT (pre_call | after_commit_pre_receipt | pre_checkpoint | post_checkpoint) for the order DAAES_KILL_ORDER; `in_flight` is armed on the API side (the
request carries X-Hold-Ms and the API raises its own marker once it has committed).

Modes:
  reference       write-ahead journal (fsynced) before every external call, receipt journal after it, atomic checkpoint; on restart reconcile every unanswered intent by asking the API for the
                  receipt of THAT operation id, and re-issue a commit only with the SAME id when the API holds none
  naive_new_key   no journal: restart from the last checkpoint and redo what the checkpoint does not show, with a NEW operation id for each attempt (the failure the matrix must expose)
  delentia        every commit is an approval-store action (create, sign by the harness's human stand-in, claim, call, mark executed); on restart the store marks silent claims OUTCOME_UNKNOWN and
                  `reconcile_by_receipt` settles them by asking the API; an action the API never saw is requested again with the same operation id and a new signature
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.daaes.events import RunLog  # noqa: E402

STAGES = ["read_orders", "validate_schema", "deduplicate", "compute_totals", "approval_list", "save_draft", "send_orders", "record_receipts", "update_status", "verify_database", "report", "close"]


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def atomic_json(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(json.dumps(obj, sort_keys=True).encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Journal:
    """Write-ahead journal: one JSON line per entry, flushed and fsynced before the call it announces."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: Dict[str, Any]) -> None:
        with open(self.path, "ab") as f:
            f.write((json.dumps(entry, sort_keys=True) + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

    def entries(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for raw in self.path.read_bytes().split(b"\n"):
            try:
                if raw.strip():
                    out.append(json.loads(raw))
            except ValueError:
                break                                               # a torn last line was never acknowledged
        return out


class Api:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.calls = {"commit": 0, "lookup": 0}

    def commit(self, op: str, business_key: str, payload: Dict[str, Any], hold_ms: int = 0) -> Dict[str, Any]:
        self.calls["commit"] += 1
        req = urllib.request.Request(self.base + "/commit", data=json.dumps({"operation_id": op, "business_key": business_key, "payload": payload}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-Hold-Ms": str(hold_ms)}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())

    def receipt(self, op: str) -> Optional[Dict[str, Any]]:
        self.calls["lookup"] += 1
        try:
            with urllib.request.urlopen(self.base + "/receipt/" + op, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise


class Hooks:
    def __init__(self, markers: Path, armed: Optional[str], order: int) -> None:
        self.markers, self.armed, self.order = markers, armed, order

    def hit(self, point: str, order: int) -> None:
        if self.armed == point and order == self.order:
            (self.markers / f"hit_{point}").write_text(str(os.getpid()), encoding="utf-8")
            time.sleep(3600)                                        # the supervisor terminates this process; it never wakes up

    def hold_ms(self, order: int) -> int:
        return 120000 if (self.armed == "in_flight" and order == self.order) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--api", type=int, required=True)
    parser.add_argument("--mode", required=True, choices=("reference", "naive_new_key", "delentia"))
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    d = Path(args.dir)
    markers = d.parent / "markers"
    hooks = Hooks(markers, os.environ.get("DAAES_KILL_POINT") or None, int(os.environ.get("DAAES_KILL_ORDER") or 1))
    api = Api(args.api)
    log = RunLog(d / "events.jsonl", args.run)
    journal = Journal(d / "journal.jsonl")
    cp_path = d / "checkpoint.json"
    orders = json.loads((d / "orders.json").read_text(encoding="utf-8"))
    intent = json.loads((d / "intent.json").read_text(encoding="utf-8"))

    resumed = cp_path.exists() or bool(log.events)
    cp: Dict[str, Any] = json.loads(cp_path.read_text(encoding="utf-8")) if cp_path.exists() else {"attempt": 0, "stage": 0, "orders": {o["id"]: "new" for o in orders}}
    cp["attempt"] += 1
    atomic_json(cp_path, cp)
    if resumed:
        log.emit("process.resumed", {"checkpoint_stage": cp["stage"], "attempt": cp["attempt"], "mode": args.mode}, intent_id=intent["intent_id"])
        if digest(intent) != json.loads((d / "intent.sha.json").read_text(encoding="utf-8"))["sha"]:
            log.emit("intent.revised", {"unauthorized": True}, intent_id=intent["intent_id"])
    else:
        log.emit("run.started", {"mode": args.mode, "orders": len(orders)}, intent_id=intent["intent_id"])
        log.emit("intent.created", {"goal": intent["goal"]}, intent_id=intent["intent_id"])

    store = None
    sign = None
    if args.mode == "delentia":
        from research.daaes import delentia_session as ds
        from rct_control_plane import approvals
        from rct_control_plane.approvals import PendingActionStore
        from rct_control_plane.persistence import ControlPlanePersistence
        key = d / "approver.pem"
        pub = approvals.generate_approver_key(str(key)) if not key.exists() else json.loads((d / "approver_pub.json").read_text(encoding="utf-8"))["pub"]
        if not (d / "approver_pub.json").exists():
            (d / "approver_pub.json").write_text(json.dumps({"pub": pub}), encoding="utf-8")
        os.environ.update({"DELENTIA_HOME": str(d / "home"), "DELENTIA_APPROVER_PUBKEYS": pub, "DELENTIA_APPROVERS_FILE": str(d / "approvers.json"), "DELENTIA_MEMORY_EMBED": "off"})
        store = PendingActionStore(ControlPlanePersistence(db_path=str(d / "agentic.db")))
        counters = {"signatures": 0}

        def sign(action: Any) -> None:
            signed = approvals.sign_decision(str(key), action.approval_id, action.action_sha256, "APPROVED")
            store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
            counters["signatures"] += 1
        del ds

        flagged = store.reconcile(older_than=0)                       # claims that never got a receipt: nobody knows whether the effect happened
        for a in flagged:
            op = a.tool_args["operation_id"]
            out = store.reconcile_by_receipt(a.approval_id, lambda act: ({"committed": True, "receipt": r} if (r := api.receipt(act.tool_args["operation_id"])) else {"committed": False, "receipt": None}))
            log.emit("tool.completed", {"tool": "reconcile", "operation_id": op, "output": out, "output_hash": digest(out)}, intent_id=intent["intent_id"])

    def mark(stage_no: int) -> None:
        cp["stage"] = max(cp["stage"], stage_no)
        atomic_json(cp_path, cp)
        log.emit("checkpoint.committed", {"stage": STAGES[stage_no - 1], "state_hash": digest(cp["orders"])}, intent_id=intent["intent_id"])

    # stages 1-6: pure preparation, each checkpointed
    for n in range(1, 7):
        if cp["stage"] < n:
            mark(n)

    run_tag = args.run
    for index, order in enumerate(orders):
        oid = order["id"]
        payload = {"order": oid, "amount": order["amount"], "currency": "THB"}
        op = f"{run_tag}-op-{oid}"
        if cp["orders"][oid] in ("committed", "closed"):
            continue
        if args.mode == "reference":
            entries = [e for e in journal.entries() if e.get("op") == op]
            has_receipt = any(e["t"] == "receipt" for e in entries)
            if any(e["t"] == "intent" for e in entries) and not has_receipt:     # an unanswered intent: ask the API about THIS operation id before anything else
                found = api.receipt(op)
                log.emit("tool.completed", {"tool": "reconcile", "operation_id": op, "output": {"found": bool(found)}, "output_hash": digest({"found": bool(found)})}, intent_id=intent["intent_id"])
                if found:
                    journal.append({"t": "receipt", "op": op, "receipt": found, "via": "reconcile"})
                    has_receipt = True
            if not has_receipt:
                journal.append({"t": "intent", "op": op, "payload_hash": digest(payload)})
                hooks.hit("pre_call", index)
                requested = log.emit("tool.requested", {"tool": "mock_api.commit", "input": {"operation_id": op, "payload_hash": digest(payload)}}, intent_id=intent["intent_id"])
                resp = api.commit(op, oid, payload, hooks.hold_ms(index))
                log.emit("tool.completed", {"tool": "mock_api.commit", "output": resp, "output_hash": digest(resp)}, causation_id=requested["event_id"], intent_id=intent["intent_id"])
                hooks.hit("after_commit_pre_receipt", index)
                journal.append({"t": "receipt", "op": op, "receipt": resp["receipt"], "via": "response"})
            cp["orders"][oid] = "committed"
            hooks.hit("pre_checkpoint", index)
            atomic_json(cp_path, cp)
            hooks.hit("post_checkpoint", index)
        elif args.mode == "naive_new_key":
            attempt_op = f"{op}-a{cp['attempt']}"
            hooks.hit("pre_call", index)
            requested = log.emit("tool.requested", {"tool": "mock_api.commit", "input": {"operation_id": attempt_op, "payload_hash": digest(payload)}}, intent_id=intent["intent_id"])
            resp = api.commit(attempt_op, oid, payload, hooks.hold_ms(index))
            log.emit("tool.completed", {"tool": "mock_api.commit", "output": resp, "output_hash": digest(resp)}, causation_id=requested["event_id"], intent_id=intent["intent_id"])
            hooks.hit("after_commit_pre_receipt", index)
            cp["orders"][oid] = "committed"
            hooks.hit("pre_checkpoint", index)
            atomic_json(cp_path, cp)
            hooks.hit("post_checkpoint", index)
        else:                                                         # delentia
            done = [a for a in store.list(status="EXECUTED", limit=500)
                    if a.tool_args.get("operation_id") == op and ((a.result or {}).get("receipt") or (a.result or {}).get("reconciled_by_person") == "done")]
            if done:
                cp["orders"][oid] = "committed"
                atomic_json(cp_path, cp)
                continue
            action = store.create("daaes", intent["goal"], "delentia_commit_order", {"operation_id": op, "business_key": oid, "payload": payload}, reason="order commit")
            sign(action)
            store.claim_for_execution(action.approval_id)
            hooks.hit("pre_call", index)
            requested = log.emit("tool.requested", {"tool": "mock_api.commit", "input": {"operation_id": op, "payload_hash": digest(payload)}}, intent_id=intent["intent_id"])
            resp = api.commit(op, oid, payload, hooks.hold_ms(index))
            log.emit("tool.completed", {"tool": "mock_api.commit", "output": resp, "output_hash": digest(resp)}, causation_id=requested["event_id"], intent_id=intent["intent_id"])
            hooks.hit("after_commit_pre_receipt", index)
            store.mark_executed(action.approval_id, {"receipt": resp["receipt"]})
            cp["orders"][oid] = "committed"
            hooks.hit("pre_checkpoint", index)
            atomic_json(cp_path, cp)
            hooks.hit("post_checkpoint", index)
    mark(9)

    # stages 10-12: verify against the API, report, close
    verified = {o["id"]: bool(api.receipt(f"{run_tag}-op-{o['id']}")) or any(e.get("t") == "receipt" for e in journal.entries()) for o in orders}
    mark(10)
    report = {"run": args.run, "orders": cp["orders"], "verified_with_api": verified, "attempts": cp["attempt"], "api_calls": api.calls}
    if args.mode == "delentia":
        report["human_signatures"] = counters["signatures"]
    atomic_json(d / "report.json", report)
    mark(11)
    for oid in cp["orders"]:
        cp["orders"][oid] = "closed"
    mark(12)
    log.emit("run.completed", {"result": "completed", "api_calls": api.calls}, intent_id=intent["intent_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
