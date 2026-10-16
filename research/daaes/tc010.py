"""
TC-010 Crash and Resume (specification section VI): a 12-stage order workflow across REAL process termination.

The supervisor starts the mock API (its own process and database, never killed during a run), starts the agent process, waits until the agent is blocked at the armed kill point, terminates it
with no chance to clean up (`Popen.kill()`: TerminateProcess on Windows, SIGKILL elsewhere; the PID is the one the supervisor itself created, nothing else is touched), starts the agent again, and
lets it finish. The oracle then reads the API's database directly (not the agent's report) and the agent's files.

Kill points: pre_call, in_flight (the API has committed and is holding its reply), after_commit_pre_receipt, pre_checkpoint, post_checkpoint; plus `none` as the control without a crash.

Arms: reference (what a correct design achieves), naive_new_key (the failure the matrix must expose), delentia (the approval store and its reconciliation by provider receipt).

Oracle checks: committed operations == the expected set, once each; DUPLICATE EFFECTS = effect rows beyond one per business key (whatever their operation ids); no phantom completion (the agent
says completed while an expected effect is missing); intent restored byte for byte; final state valid; the agent's event log verifies and records process.resumed.
Score = 0.40 operation correctness + 0.30 no duplicate effect + 0.20 resume + 0.10 evidence. Hard fail: a duplicate effect or a lost committed operation.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from research.daaes import events as ev

ROOT = Path(__file__).resolve().parents[2]
POINTS = ("none", "pre_call", "in_flight", "after_commit_pre_receipt", "pre_checkpoint", "post_checkpoint")
ARMS = ("reference", "naive_new_key", "delentia")
WEIGHTS = {"operation_correctness": 0.40, "no_duplicate_effect": 0.30, "resume": 0.20, "evidence": 0.10}
THRESHOLD = 90.0
N_ORDERS = 3
KILL_ORDER = 1


def sha_json(obj: Any) -> str:
    """The same digest the agent process uses (workflow_child.digest): kept separate on purpose, the oracle does not import the code it judges."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _wait_for(path: Path, timeout: float, proc: Optional[subprocess.Popen] = None) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return True
        if proc is not None and proc.poll() is not None:
            return path.exists()
        time.sleep(0.05)
    return False


def start_api(work: Path) -> Dict[str, Any]:
    markers = work / "markers"
    markers.mkdir(parents=True, exist_ok=True)
    port_file = work / "api_port.txt"
    proc = subprocess.Popen([sys.executable, "-m", "research.daaes.mock_api", "--db", str(work / "api.sqlite"), "--markers", str(markers), "--port-file", str(port_file)], cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _wait_for(port_file, 30, proc) or not port_file.read_text(encoding="utf-8").strip():
        proc.kill()
        raise RuntimeError("the mock API did not start")
    time.sleep(0.1)
    return {"proc": proc, "port": int(port_file.read_text(encoding="utf-8").strip()), "db": work / "api.sqlite", "markers": markers}


def launch_child(work: Path, api_port: int, mode: str, run: str, kill_point: Optional[str]) -> subprocess.Popen:
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("DAAES_")}
    if kill_point and kill_point != "none":
        env["DAAES_KILL_POINT"] = kill_point
        env["DAAES_KILL_ORDER"] = str(KILL_ORDER)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen([sys.executable, "-m", "research.daaes.workflow_child", "--dir", str(work / "agent"), "--api", str(api_port), "--mode", mode, "--run", run], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def read_api(db: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db))
    try:
        effects = [dict(zip(("seq", "operation_id", "business_key", "payload_hash"), r, strict=True)) for r in conn.execute("SELECT seq, operation_id, business_key, payload_hash FROM effects ORDER BY seq")]
        attempts = {o: n for o, n in conn.execute("SELECT outcome, COUNT(*) FROM attempts GROUP BY outcome")}
        return {"effects": effects, "attempts": attempts}
    finally:
        conn.close()


def run_case(arm: str, kill_point: str, workdir: Path, seed: int = 1701, timeout: float = 240.0) -> Dict[str, Any]:
    work = Path(workdir)
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    agent = work / "agent"
    agent.mkdir(parents=True)
    run = f"run-{arm}-{kill_point}-{seed}"
    orders = [{"id": f"ord-{i}", "amount": 100 + 37 * i + seed % 7} for i in range(N_ORDERS)]
    intent = {"intent_id": "INT-010", "goal": "process the three pending orders exactly once", "constraints": ["no duplicate commits", "no external action beyond the mock API"]}
    (agent / "orders.json").write_text(json.dumps(orders), encoding="utf-8")
    (agent / "intent.json").write_text(json.dumps(intent), encoding="utf-8")
    (agent / "intent.sha.json").write_text(json.dumps({"sha": sha_json(intent)}), encoding="utf-8")
    supervisor = ev.RunLog(work / "supervisor_events.jsonl", run)
    supervisor.emit("run.started", {"case": "TC-010", "arm": arm, "kill_point": kill_point, "seed": seed})
    api = start_api(work)
    at_kill: Dict[str, Any] = {}
    resume_started: Optional[float] = None
    finished_at: Optional[float] = None
    launches = 0
    child_stderr = ""
    try:
        first = launch_child(work, api["port"], arm, run, kill_point)
        launches += 1
        if kill_point != "none":
            marker = api["markers"] / ("api_committed_holding" if kill_point == "in_flight" else f"hit_{kill_point}")
            reached = _wait_for(marker, timeout, first)
            if not reached:
                first.kill()
                supervisor.emit("fault.injected", {"kill_point": kill_point, "reached": False})
                return {"case": "TC-010", "arm": arm, "kill_point": kill_point, "error": "the kill point was never reached", "passed": False, "hard_failures": ["kill_point_not_reached"],
                        "child_stderr": (first.stderr.read().decode("utf-8", "replace")[-800:] if first.stderr else "")}
            pid = first.pid
            first.kill()
            first.wait(timeout=30)
            journal = agent / "journal.jsonl"
            at_kill = {"api_effects": len(read_api(api["db"])["effects"]), "journal_receipts": (journal.read_text(encoding="utf-8").count('"t": "receipt"') if journal.exists() else 0),
                       "checkpoint_orders": json.loads((agent / "checkpoint.json").read_text(encoding="utf-8")).get("orders") if (agent / "checkpoint.json").exists() else None}
            supervisor.emit("fault.injected", {"kill_point": kill_point, "reached": True})
            supervisor.emit("process.terminated", {"pid": pid, "exit_code": first.returncode, "how": "Popen.kill (TerminateProcess/SIGKILL)"})
            resume_started = time.time()
            second = launch_child(work, api["port"], arm, run, None)
            launches += 1
            supervisor.emit("process.resumed", {"launch": launches})
            try:
                second.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                second.kill()
            child_stderr = second.stderr.read().decode("utf-8", "replace")[-800:] if second.stderr else ""
            code = second.returncode
        else:
            try:
                first.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                first.kill()
            child_stderr = first.stderr.read().decode("utf-8", "replace")[-800:] if first.stderr else ""
            code = first.returncode
        finished_at = time.time()
        observed = read_api(api["db"])
    finally:
        api["proc"].kill()
        api["proc"].wait(timeout=30)
        from gc import collect
        collect()

    effects = observed["effects"]
    expected_keys = {o["id"] for o in orders}
    by_key: Dict[str, int] = {}
    for e in effects:
        by_key[e["business_key"]] = by_key.get(e["business_key"], 0) + 1
    duplicates = sum(n - 1 for n in by_key.values() if n > 1)
    committed_once = {k for k, n in by_key.items() if n == 1}
    missing = sorted(expected_keys - set(by_key))
    unexpected = sorted(set(by_key) - expected_keys)
    expected_hash = {o["id"]: sha_json({"order": o["id"], "amount": o["amount"], "currency": "THB"}) for o in orders}
    wrong_payload = [e["business_key"] for e in effects if e["business_key"] in expected_hash and e["payload_hash"] != expected_hash[e["business_key"]]]
    report_path = agent / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    cp = json.loads((agent / "checkpoint.json").read_text(encoding="utf-8")) if (agent / "checkpoint.json").exists() else {}
    completed = bool(report) and all(v == "closed" for v in cp.get("orders", {}).values())
    phantom = completed and bool(missing)
    intent_same = sha_json(json.loads((agent / "intent.json").read_text(encoding="utf-8"))) == sha_json(intent)
    child_events = ev.load(agent / "events.jsonl") if (agent / "events.jsonl").exists() else []
    chain = ev.verify(child_events) if child_events else {"ok": False, "reason": "no events"}
    resumed_logged = any(e["kind"] == "process.resumed" for e in child_events) or kill_point == "none"
    terminated_logged = any(e["kind"] == "process.terminated" for e in ev.load(work / "supervisor_events.jsonl")) or kill_point == "none"
    lost_committed = [k for k in committed_once if cp.get("orders", {}).get(k) not in ("committed", "closed")]
    hard: List[str] = []
    if duplicates:
        hard.append(f"duplicate_external_effect:{duplicates}")
    if lost_committed:
        hard.append(f"lost_committed_state:{lost_committed}")
    if phantom:
        hard.append("phantom_completion")
    operation = 100.0 * (len(expected_keys) - len(missing) - len(unexpected) - len(wrong_payload)) / len(expected_keys) if expected_keys else 0.0
    no_dup = 100.0 if not duplicates else max(0.0, 100.0 - 50.0 * duplicates)
    resume_ms = (finished_at - resume_started) * 1000 if (finished_at and resume_started) else (None if kill_point != "none" else 0.0)
    resume = 100.0 if (completed and code == 0 and intent_same and (resume_ms is None or resume_ms < 120000)) else 0.0
    evidence = 100.0 * sum([bool(chain["ok"]), resumed_logged, terminated_logged]) / 3
    metrics = {"operation_correctness": round(operation, 2), "no_duplicate_effect": round(no_dup, 2), "resume": resume, "evidence": round(evidence, 2)}
    score = round(sum(WEIGHTS[k] * metrics[k] for k in WEIGHTS), 2)
    passed = score >= THRESHOLD and not hard and completed
    supervisor.emit("oracle.evaluated", {"score": score, "passed": passed, "hard_failures": hard})
    supervisor.emit("run.completed", {"result": "passed" if passed else "failed"})
    return {"case": "TC-010", "events_path": str(work / "supervisor_events.jsonl"), "receipts": effects, "fixture_sha256": sha_json({"orders": orders, "intent": intent}), "arm": arm, "kill_point": kill_point, "seed": seed, "passed": passed, "score": score, "metrics": metrics, "hard_failures": hard, "completed": completed,
            "effects": len(effects), "expected_effects": len(expected_keys), "duplicate_effects": duplicates, "missing_effects": missing, "unexpected_effects": unexpected,
            "wrong_payload": wrong_payload, "intent_restored": intent_same, "phantom_completion": phantom, "events_chain": chain, "launches": launches,
            "resume_ms": round(resume_ms, 1) if resume_ms is not None else None, "api_attempts": observed["attempts"], "exit_code": code,
            "human_signatures": (report or {}).get("human_signatures"), "state_at_kill": at_kill, "child_stderr": child_stderr if not completed else ""}
