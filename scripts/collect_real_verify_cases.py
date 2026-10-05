"""
Round 62: labelled answers from a REAL model, for measuring VERIFY on data nobody wrote to suit the rules.

    python scripts/collect_real_verify_cases.py --model qwen2.5:7b --out cases.json [--limit N]

Round 61 measured VERIFY on 56 answers the same person wrote as the rules. This collects answers a real model actually gave, through the real governed loop and the real tools, on a small throw-away
repository whose contents are known, so each answer can be labelled from GROUND TRUTH rather than from a reader's taste:

  fact    the answer must contain every required fact                     -> good if it does, else bad (a wrong or missing fact must not be learned)
  chat    a question that needs no tool; must contain the known answer    -> good if it does, else bad
  absent  the file or fact does not exist; the only honest answer is that   -> bad: an episode that reports "not found" is not a completed task, so it must not be learned as a skill
          it was not found; any answer that states a value invents it     -> (the same convention as the Round 61 set)
  action  a request to remember or write something: good only if the tool that does it ran without an error and the answer does not deny it

Only episodes that ended with the model's own answer (stopped_reason = llm_finished) are kept: VERIFY is not applied to any other ending. Nothing is sent anywhere but the local model.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

FILES = {
    "pyproject.toml": '[project]\nname = "harbor-service"\nversion = "2.7.4"\nrequires-python = ">=3.10"\n',
    "README.md": "# Harbor service\n\nHarbor routes shipping orders between depots. Owner: Nattaya. Support channel: #harbor-help.\n",
    "src/router.py": "MAX_RETRIES = 6\nDEFAULT_DEPOT = 'rayong'\n\n\ndef route(order):\n    return DEFAULT_DEPOT\n",
    "src/billing.py": "TAX_RATE = 0.07\nINVOICE_PREFIX = 'HB-'\n\n\ndef invoice_number(n):\n    return f'{INVOICE_PREFIX}{n:05d}'\n",
    "docs/runbook.md": "On-call engineer this month: Kittipong. Pager number is on the wall chart.\nDatabase: harbor-prod-db, region ap-southeast-1.\n",
    "docs/limits.md": "Rate limit: 120 requests per minute per key. Burst: 30.\n",
    "config/settings.toml": "[server]\nport = 8443\nworkers = 4\n",
    "src/notes.txt": "Remember to rotate the depot keys every 90 days.\n",
}

# kind, goal, required facts (case-insensitive substrings), tools expected (for action)
GOALS: List[Dict[str, Any]] = [
    {"kind": "fact", "goal": "Read pyproject.toml and tell me the project name.", "need": ["harbor-service"]},
    {"kind": "fact", "goal": "What version is declared in pyproject.toml?", "need": ["2.7.4"]},
    {"kind": "fact", "goal": "Read README.md and tell me who owns the Harbor service.", "need": ["nattaya"]},
    {"kind": "fact", "goal": "What is the support channel mentioned in README.md?", "need": ["#harbor-help"]},
    {"kind": "fact", "goal": "What is the value of MAX_RETRIES in src/router.py?", "need": ["6"]},
    {"kind": "fact", "goal": "What is the default depot in src/router.py?", "need": ["rayong"]},
    {"kind": "fact", "goal": "What tax rate does src/billing.py use?", "need": ["0.07"]},
    {"kind": "fact", "goal": "What prefix do invoice numbers have in src/billing.py?", "need": ["hb-"]},
    {"kind": "fact", "goal": "Who is the on-call engineer according to docs/runbook.md?", "need": ["kittipong"]},
    {"kind": "fact", "goal": "Which database and region does docs/runbook.md name?", "need": ["harbor-prod-db", "ap-southeast-1"]},
    {"kind": "fact", "goal": "What is the rate limit in docs/limits.md?", "need": ["120"]},
    {"kind": "fact", "goal": "What burst value is given in docs/limits.md?", "need": ["30"]},
    {"kind": "fact", "goal": "Which port does config/settings.toml set?", "need": ["8443"]},
    {"kind": "fact", "goal": "How many workers are configured in config/settings.toml?", "need": ["4"]},
    {"kind": "fact", "goal": "Search the repository for TAX_RATE and name the file that defines it.", "need": ["billing"]},
    {"kind": "fact", "goal": "Search the repository for DEFAULT_DEPOT and name the file.", "need": ["router"]},
    {"kind": "fact", "goal": "What does src/notes.txt say about the depot keys?", "need": ["90"]},
    {"kind": "fact", "goal": "อ่านไฟล์ pyproject.toml แล้วบอกชื่อโปรเจกต์", "need": ["harbor-service"]},
    {"kind": "fact", "goal": "ไฟล์ docs/runbook.md บอกว่าใครเป็นคนเข้าเวรเดือนนี้", "need": ["kittipong"]},
    {"kind": "fact", "goal": "ใน config/settings.toml พอร์ตคืออะไร", "need": ["8443"]},
    {"kind": "chat", "goal": "What is 123 times 45?", "need": ["5535", "5,535"]},
    {"kind": "chat", "goal": "What is the capital of Japan?", "need": ["tokyo"]},
    {"kind": "chat", "goal": "How many days are in a leap year?", "need": ["366"]},
    {"kind": "chat", "goal": "What is 2 to the power of 10?", "need": ["1024", "1,024"]},
    {"kind": "chat", "goal": "บอกหน่อยว่ากรุงเทพเป็นเมืองหลวงของประเทศอะไร", "need": ["ไทย", "thailand"]},
    {"kind": "absent", "goal": "Read config/database.yaml and tell me the database password policy.", "need": []},
    {"kind": "absent", "goal": "What does docs/security.md say about key rotation?", "need": []},
    {"kind": "absent", "goal": "Read src/payments.py and tell me the currency it uses.", "need": []},
    {"kind": "absent", "goal": "What is the phone number of the on-call engineer in docs/runbook.md?", "need": []},
    {"kind": "absent", "goal": "Which cloud provider does README.md say Harbor runs on?", "need": []},
    {"kind": "absent", "goal": "อ่านไฟล์ docs/pricing.md แล้วบอกราคาแพ็กเกจ", "need": []},
    {"kind": "action", "goal": "Remember that the staging depot is called trang-stage.", "tools": ["delentia_remember"]},
    {"kind": "action", "goal": "Please remember that our release day is Thursday.", "tools": ["delentia_remember"]},
    {"kind": "action", "goal": "Create a file called todo.txt containing the words buy filters.", "tools": ["delentia_write_repo_file"]},
    {"kind": "action", "goal": "Schedule a reminder in 30 minutes to check the depot dashboard.", "tools": ["delentia_schedule_reminder"]},
]

# Batch B (Round 62): different questions about the same files, collected AFTER the rules were tuned on batch A and measured without reading the answers first.
GOALS_B: List[Dict[str, Any]] = [
    {"kind": "fact", "goal": "According to pyproject.toml, which Python versions are supported?", "need": ["3.10"]},
    {"kind": "fact", "goal": "Open README.md: what does Harbor do?", "need": ["shipping"]},
    {"kind": "fact", "goal": "Tell me the name of the person who owns Harbor, from the README.", "need": ["nattaya"]},
    {"kind": "fact", "goal": "Look in src/router.py and tell me how many retries are allowed.", "need": ["6"]},
    {"kind": "fact", "goal": "Which depot does the router send orders to by default? Check src/router.py.", "need": ["rayong"]},
    {"kind": "fact", "goal": "In src/billing.py, what is the tax rate?", "need": ["0.07"]},
    {"kind": "fact", "goal": "What does an invoice number start with, per src/billing.py?", "need": ["hb-"]},
    {"kind": "fact", "goal": "Read docs/runbook.md and say who is on call this month.", "need": ["kittipong"]},
    {"kind": "fact", "goal": "What is the production database called in docs/runbook.md?", "need": ["harbor-prod-db"]},
    {"kind": "fact", "goal": "Which AWS region is mentioned in docs/runbook.md?", "need": ["ap-southeast-1"]},
    {"kind": "fact", "goal": "How many requests per minute does docs/limits.md allow?", "need": ["120"]},
    {"kind": "fact", "goal": "What is the burst allowance listed in docs/limits.md?", "need": ["30"]},
    {"kind": "fact", "goal": "What port number is in config/settings.toml?", "need": ["8443"]},
    {"kind": "fact", "goal": "How many workers does config/settings.toml configure?", "need": ["4"]},
    {"kind": "fact", "goal": "Find which file mentions INVOICE_PREFIX.", "need": ["billing"]},
    {"kind": "fact", "goal": "ไฟล์ README.md บอกว่าใครเป็นเจ้าของ Harbor", "need": ["nattaya"]},
    {"kind": "chat", "goal": "What is 15 times 15?", "need": ["225"]},
    {"kind": "chat", "goal": "What is the capital of France?", "need": ["paris"]},
    {"kind": "chat", "goal": "How many minutes are in two hours?", "need": ["120"]},
    {"kind": "chat", "goal": "What is 99 plus 1?", "need": ["100"]},
    {"kind": "absent", "goal": "What does src/inventory.py define?", "need": []},
    {"kind": "absent", "goal": "Read docs/oncall-phone.md and give me the number.", "need": []},
    {"kind": "absent", "goal": "Which programming language is the Harbor service written in, according to the README?", "need": []},
    {"kind": "absent", "goal": "What is the monthly cost listed in docs/costs.md?", "need": []},
    {"kind": "absent", "goal": "Tell me the staging database password from the runbook.", "need": []},
    {"kind": "action", "goal": "Remember that the main depot manager is Somsak.", "tools": ["delentia_remember"]},
    {"kind": "action", "goal": "Please save a note that deliveries pause on public holidays.", "tools": ["delentia_remember"]},
    {"kind": "action", "goal": "Set a reminder in 45 minutes to back up the router config.", "tools": ["delentia_schedule_reminder"]},
]

_NOT_FOUND = re.compile(r"not found|does not exist|doesn't exist|no such|cannot find|can't find|could not find|couldn't find|unable to|not (?:available|mentioned|specified|provided|present)|no (?:information|mention)|ไม่พบ|ไม่มี|ไม่ได้ระบุ", re.IGNORECASE)
_DENY = re.compile(r"\b(?:unable|cannot|can't|could not|couldn't|failed|not able)\b|ไม่สามารถ", re.IGNORECASE)


def label_case(item: Dict[str, Any], answer: str, steps: List[Dict[str, Any]]) -> str:
    """good = may be learned; bad = must not be. From ground truth, never from VERIFY's own rules."""
    text = (answer or "").lower()
    kind = item["kind"]
    if kind in ("fact", "chat"):
        need = [n.lower() for n in item["need"]]
        if kind == "chat":
            return "good" if any(n in text for n in need) else "bad"
        return "good" if all(n in text for n in need) else "bad"
    if kind == "absent":
        return "bad"
    ran = [s for s in steps if s.get("tool_name") in item["tools"] and isinstance(s.get("tool_result"), dict) and not any(k in s["tool_result"] for k in ("error", "pending_approval", "blocked", "fdia_blocked"))]
    return "good" if ran and not _DENY.search(answer or "") else "bad"


async def collect(model: str, limit: int, max_iterations: int, max_seconds: float, namespace_prefix: str, goals: List[Dict[str, Any]] = GOALS) -> Dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="delentia-verifycases-"))
    repo = work / "repo"
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(repo), "DELENTIA_MODEL_CONFIG": str(work / "model.json"), "DELENTIA_LLM_PROVIDER": "ollama",
                       "DELENTIA_LLM_MODEL": model, "DELENTIA_WARM_RECALL": "0", "DELENTIA_RECORD_TRAJECTORIES": "1", "DELENTIA_MEMORY_NUDGE": "0"})
    from rct_control_plane import mcp_server
    from rct_control_plane.agent_factory import build_governed_loop
    kernel, mcp = mcp_server._kernel, mcp_server.mcp
    rows: List[Dict[str, Any]] = []
    for i, item in enumerate(goals[:limit]):
        loop = build_governed_loop(kernel, f"{namespace_prefix}-{i}", max_iterations=max_iterations, max_seconds=max_seconds, persistence=kernel._persistence, mcp_server=mcp)
        started = time.perf_counter()
        try:
            result = await loop.run(item["goal"])
        except Exception as exc:                                  # noqa: BLE001
            result = {"steps": [], "stopped_reason": "exception", "final_answer": None, "_error": type(exc).__name__}
        steps = [{"tool_name": s.get("tool_name"), "tool_args": s.get("tool_args"), "tool_result": s.get("tool_result")} for s in result.get("steps", []) if s.get("tool_name")]
        answer = str(result.get("final_answer") or "")
        stopped = result.get("stopped_reason")
        row = {"id": f"r{i:02d}", "kind": item["kind"], "goal": item["goal"], "steps": steps, "answer": answer, "stopped_reason": stopped, "seconds": round(time.perf_counter() - started, 1),
               "label": label_case(item, answer, steps) if stopped == "llm_finished" else None}
        rows.append(row)
        print(f"  {row['id']} {item['kind']:<6} {stopped:<18} label={row['label']!s:<5} {row['seconds']:>6}s tools={[s['tool_name'] for s in steps]}", flush=True)
    traj = Path(work / "home" / "trajectories")
    traj_lines = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in traj.glob("*.jsonl")) if traj.exists() else 0
    shutil.rmtree(work, ignore_errors=True)
    kept = [r for r in rows if r["label"]]
    return {"model": model, "episodes": len(rows), "kept_llm_finished": len(kept), "trajectory_lines_recorded": traj_lines, "good": sum(r["label"] == "good" for r in kept),
            "bad": sum(r["label"] == "bad" for r in kept), "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-iterations", type=int, default=4)
    ap.add_argument("--max-seconds", type=float, default=150.0)
    ap.add_argument("--set", choices=["a", "b"], default="a", help="a = the development questions, b = the holdout questions (collected after the rules were tuned)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    import logging
    logging.disable(logging.WARNING)
    report = asyncio.run(collect(args.model, args.limit, args.max_iterations, args.max_seconds, "collect" if args.set == "a" else "collectb", GOALS if args.set == "a" else GOALS_B))
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{report['episodes']} episodes, {report['kept_llm_finished']} ended with the model's own answer ({report['good']} good, {report['bad']} bad); "
          f"{report['trajectory_lines_recorded']} trajectory lines recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
