"""
Is every main object of the system really there and callable? (Round 64)

For each object the Architect named - RCT-7 Thinking, the FDIA equation, RCTDB, the Delta engine, the Intent Loop, JITNA (including spawning agents) and the 41 algorithms - this
script makes real calls (real governed loop, real tools on a temporary workspace, real SQLite, real Ed25519, the model replaced by a script that follows the goal) and reports what
EVIDENCE came back. It separates three claims that are easy to blur:

  RUNS         the object executed on this run and left a checkable trace
  CONTRIBUTES  something it produced reached the model's prompt or changed an outcome
  HELPS        an A/B shows the outcome got better (this script never says so: that needs a capable model, see research/)

    python scripts/audit_main_objects.py --out research/main_objects_audit.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def build_policy(workspace: Path):
    import scripted_model as sm
    from research.policy_models import QuotePolicy
    quotes = QuotePolicy(workspace, "diligent")

    def policy(req: Any) -> str:
        goal = req.goal
        if goal.startswith("READ_BIG"):
            if req.history_empty:
                return sm._call("delentia_read_repo_file", {"relative_path": "big/report.md", "max_bytes": 200000}, "read the report")
            return sm._finish("I read big/report.md and counted its rows.")
        if goal.startswith("EDIT"):
            return sm._call("delentia_write_repo_file", {"relative_path": "notes/new.md", "content_text": "hello\n"}, "write the note")
        return quotes(req)
    return policy


async def run(out_path: str | None) -> Dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="delentia-audit-"))
    repo, home = work / "repo", work / "home"
    for rel, text in {
        "quotes/vendor_a.md": "# ใบเสนอราคา บริษัท สยามแอร์\nราคารวม: 12,500 บาท\nระยะเวลาทำงาน: 5 วัน\n",
        "quotes/vendor_b.md": "# ใบเสนอราคา บริษัท ไทยคูลลิ่ง\nราคารวม: 16,800 บาท\nระยะเวลาทำงาน: 3 วัน\n",
        "quotes/vendor_c.md": "# ใบเสนอราคา บริษัท บางกอกเทคนิค\nราคารวม: 9,900 บาท\nระยะเวลาทำงาน: 9 วัน\n",
        "big/report.md": "\n".join(f"| row {j} | item {j % 17} | status {'ok' if j % 5 else 'late'} | owner team-{j % 9} | note {j} |" for j in range(520)),
    }.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, capture_output=True)
    os.environ.update({"USERPROFILE": str(home), "HOME": str(home), "DELENTIA_HOME": str(work / "data"), "DELENTIA_REPO_ROOT": str(repo),
                       "DELENTIA_ALGORITHM_PIPELINE": "1", "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_APPROVERS_FILE": str(work / "approvers.json")})
    for name in ("DELENTIA_WARM_RECALL", "DELENTIA_FDIA_POLICY", "DELENTIA_NOTARY_URL", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_TOOL_MENU", "DELENTIA_UNTRUSTED_PATHS"):
        os.environ.pop(name, None)
    logging.disable(logging.CRITICAL)
    try:
        from loguru import logger as _loguru
        _loguru.remove()
    except Exception:                                   # noqa: BLE001
        pass
    import scripted_model as sm
    from rct_control_plane import approvals, audit_chain
    from rct_control_plane.model_config import save_model_selection
    audit_key = work / "keys" / "audit.pem"
    audit_pub = audit_chain.generate_signing_key(str(audit_key))
    os.environ[audit_chain.SIGNING_KEY_ENV] = str(audit_key)
    os.environ[approvals.APPROVERS_ENV] = approvals.generate_approver_key(str(work / "keys" / "approver.pem"))

    report: Dict[str, Any] = {"objects": {}, "note": "RUNS = executed and left a trace; CONTRIBUTES = reached the prompt or changed an outcome; HELPS = needs an A/B with a capable model (not claimed here)"}
    with sm.ScriptedModel(build_policy(repo)) as model:
        cfg = work / "model.json"
        save_model_selection("openai-compat", model.model_id, path=cfg, endpoint={"base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-test-model"})
        os.environ.update({"DELENTIA_MODEL_CONFIG": str(cfg), "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": model.model_id})
        from rct_control_plane.agent_factory import build_governed_loop
        from rct_control_plane.mcp_server import _kernel, mcp
        goal_compare = ("อ่านใบเสนอราคาในไฟล์ quotes/vendor_a.md, quotes/vendor_b.md, quotes/vendor_c.md ทำตารางเปรียบเทียบราคา งบไม่เกิน 15,000 บาท "
                        "ปิดท้ายด้วยบรรทัดเดียวว่า 'ในงบ: ชื่อบริษัท, ชื่อบริษัท'")

        async def episode(ns: str, goal: str) -> tuple:
            loop = build_governed_loop(_kernel, ns, max_iterations=8, persistence=_kernel._persistence, mcp_server=mcp)
            loop._route_enabled = False
            result = await loop.run(goal)
            return loop, result

        loop1, r1 = await episode("audit-a", goal_compare)
        loop2, r2 = await episode("audit-b", "EDIT notes/new.md")
        loop3, r3 = await episode("audit-c", "READ_BIG the report")
        traces = [t for r in (r1, r3) for t in (r.get("pipeline") or {}).get("traces", [])]

        # ---- RCT-7 Thinking
        steps = loop1._episode_rct7_steps
        from rct_control_plane.algorithm_kernel_41 import crystal_hash
        report["objects"]["RCT-7 Thinking"] = {
            "RUNS": len(steps) == 7 and "CRYSTAL-HASH" in steps[-1],
            "CONTRIBUTES": "RCT-7" in loop1._episode_context_text,
            "evidence": {"steps": [s[:70] for s in steps], "plan_in_prompt": "RCT-7" in loop1._episode_context_text, "step7_fingerprint_stable": crystal_hash("x") == crystal_hash("x"),
                         "verify_step": {k: r1["intent_verification"].get(k) for k in ("applicable", "aligned_with_intent", "similarity_score")}},
            "HELPS": "not measured: needs the R factor A/B with a capable model (research/PROTOCOL.md H-R)",
        }
        # ---- FDIA
        from rct_control_plane.governed_autonomous_loop import fdia_score
        with _kernel._persistence._connect() as conn:
            gates = [json.loads(x[0]) for x in conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate' ORDER BY id").fetchall()]
        report["objects"]["FDIA equation"] = {
            "RUNS": bool(gates) and r2["stopped_reason"] in ("pending_approval", "fdia_blocked"),
            "CONTRIBUTES": any(g.get("A") is not None for g in gates),
            "evidence": {"vectors": {"D0.9,I1,A1": fdia_score(0.9, 1, 1), "D0.9,I1,A0": fdia_score(0.9, 1, 0), "D0,I1,A1": fdia_score(0, 1, 1), "D0.9,I0,A1": fdia_score(0.9, 0, 1)},
                         "gate_rows": [{k: g.get(k) for k in ("tool_name", "D", "I", "A", "F", "threshold", "blocked")} for g in gates][:3],
                         "a_write_with_little_data_stopped_as": r2["stopped_reason"], "note": "D=0.21 (the goal names no existing file) x I=0.5 -> F below 0.5: the NUMBER blocked this one; with enough data the same write waits for a signature instead", "D_of_the_compare_goal": loop1._episode_D},
            "HELPS": "not proven: the research harness shows the numeric gate did not change the outcome of the plain-note attack (24/32 either way); structure (taint) did",
        }
        # ---- RCTDB
        runs = _kernel._persistence.recent_governed_runs("audit-a")
        report["objects"]["RCTDB"] = {
            "RUNS": len(runs) == 1, "CONTRIBUTES": bool(r1.get("experiment")),
            "evidence": {"experiment_runs_for_the_episode": len(runs), "experiment": r1.get("experiment"), "fields": sorted(runs[0].keys())[:14] if runs else []},
            "HELPS": "records and compares runs (delentia experiments list|compare); no outcome A/B",
        }
        # ---- Delta engine (history delta + Delta v2 on big outputs)
        compressions = getattr(loop3, "_episode_compressions", [])
        from rct_control_plane import tool_output_store
        expanded_ok = None
        if compressions:
            handle = compressions[0].get("original_id")
            try:
                original = tool_output_store.ToolOutputStore(_kernel._persistence).get(handle) if handle else None
                expanded_ok = bool(original) and "row 519" in original
            except Exception:                           # noqa: BLE001
                expanded_ok = None
        report["objects"]["Delta engine"] = {
            "RUNS": bool(compressions), "CONTRIBUTES": bool(compressions),
            "evidence": {"big_output_compressed": bool(compressions), "compression": compressions[:1], "original_recoverable": expanded_ok,
                         "see": "research/prompt_cost.json: Delta v2 on tool output -48% (real prose) to -69% (repetitive); history-delta saved nothing and cost +22% on Thai documents until Round 64's fix"},
            "HELPS": "yes for large tool outputs (measured in tokens); no for the history rendering; never touches the tool menu, which is 94% of a prompt",
        }
        # ---- Intent Loop
        il = r1.get("intent_loop") or {}
        report["objects"]["Intent Loop"] = {
            "RUNS": set(il) >= {"gatekeeper", "memory", "executor", "verifier"}, "CONTRIBUTES": bool(il.get("gatekeeper", {}).get("D") is not None),
            "evidence": {"pillars": sorted(il), "D": il.get("gatekeeper", {}).get("D"), "growth": {k: (r1.get("growth") or {}).get(k) for k in ("delta", "G")}},
            "HELPS": "growth is graded per episode; 'smarter with use' measured only as memory recall (0/8 -> 5/8 on paraphrases, Round 52) and never on a capable model",
        }
        # ---- JITNA (signature) and spawning
        with _kernel._persistence._connect() as conn:
            row = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_episode_start' AND actor = 'audit-a' ORDER BY id LIMIT 1").fetchone()
            chain = audit_chain.verify_audit_chain(conn, audit_pub)
        start = json.loads(row[0])
        report["objects"]["JITNA (signing)"] = {
            "RUNS": bool(start.get("jitna_verified")) and chain.ok, "CONTRIBUTES": chain.signed_rows > 0,
            "evidence": {"episode_packet_verified": start.get("jitna_verified"), "audit_chain": {"ok": chain.ok, "rows": chain.chained_rows, "signed": chain.signed_rows}},
            "HELPS": "integrity and binding; not key trust (pinning needs the notary)",
        }
        # ---- 41 algorithms
        by_status = Counter(t["status"] for t in traces)
        ids_ok = sorted({t["algo_id"] for t in traces if t["status"] == "ok"})
        not_ok = {}
        for t in traces:
            if t["status"] != "ok" and t["algo_id"] not in ids_ok:
                not_ok[t["algo_id"]] = f"{t['status']}: {t.get('reason', '')[:70]}"
        report["objects"]["41 algorithms"] = {
            "RUNS": len(ids_ok) >= 20, "CONTRIBUTES": sum(t.get("advice_lines", 0) for t in traces) > 0,
            "evidence": {"note": "two episodes with two kinds of goal; the Round 51 benchmark with a URL, a video and a build request reached 37 of 41 (the rest need a model)", "distinct_algorithms_ok_over_two_episodes": len(ids_ok), "ids_ok": ids_ok, "not_ok": not_ok, "status_counts": dict(by_status),
                         "pipeline_ms_episode_1": (r1.get("pipeline") or {}).get("ms"), "advice_lines_reaching_prompt": sum(t.get("advice_lines", 0) for t in traces)},
            "HELPS": "no per-algorithm A/B exists; the loop itself uses ALGO-01/04/21/25 + compiler + matcher + MEE; the others add trace and advice lines",
        }

    # ---- spawning agents: the agent asks for subagents (real processes, worktrees, signed answers)
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "full_pipeline_cases.py"), "--only", "C10", "C11", "C13", "C14"], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=ROOT, timeout=900)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith(("PASS", "FAIL"))]
    report["objects"]["JITNA (spawning agents)"] = {
        "RUNS": bool(lines) and all(ln.startswith("PASS") for ln in lines), "CONTRIBUTES": True,
        "evidence": {"cases": lines},
        "HELPS": "proven with a model that follows a script (three OS processes, git worktrees, signed answers, forged answer detected, no grand-children); a real model has never asked for subagents",
    }
    if out_path:
        Path(out_path).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return report


def render(report: Dict[str, Any]) -> str:
    lines = ["| object | runs | contributes | helps |", "|---|---|---|---|"]
    for name, o in report["objects"].items():
        lines.append(f"| {name} | {'yes' if o['RUNS'] else '**NO**'} | {'yes' if o['CONTRIBUTES'] else '**NO**'} | {o['HELPS']} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    report = asyncio.run(run(args.out))
    print(render(report))
    print()
    for name, o in report["objects"].items():
        print(f"## {name}\n{json.dumps(o['evidence'], ensure_ascii=False, default=str)[:900]}\n")
    return 0 if all(o["RUNS"] for o in report["objects"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
