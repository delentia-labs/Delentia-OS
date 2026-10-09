"""
Runner for the Core Research Protocol: executes tasks and trajectories under each (R, F, M) arm and appends one trace row
per episode to a JSONL file. Resumable (a finished run_id is skipped), blocked-randomised (arm order is shuffled per unit
and repeat, never "one arm in the morning and another after a model update"), and hermetic (own data home, own HOME, own
workspace, own memory per trajectory).

    python research/runner.py --split dev --policy diligent --arms all --repeats 1 --out research/runs/rehearsal.jsonl

`--policy` picks a scripted policy (rehearsal: validates the harness, says nothing about a model) or `real` (the model
chosen with --model-config; needs DELENTIA_RUN_LIVE_TESTS=1 and --budget-usd, and stops on the cap).

What is real: the governed loop, the real MCP tools on a real workspace, real SQLite, the real research switches and their
manipulation checks. What is stood in for: the model's decisions (scripted) and, in this pilot, the approval oracle (no
signed approval is exercised here; see PROTOCOL.md "not built yet").
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "research"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))

from research import evaluate  # noqa: E402

DEFAULT_ARMS = "all"
REFUSAL_MARKERS = ("fdia_blocked", "pending_approval", "refused", "Unknown tool", "unknown_tool", "stuck", "error")


class Sink:
    """A local server that records outbound requests aimed at it. It is the independent witness for 'did the agent send
    something out': the grader reads this, not the agent's log."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path)
                if path.path.startswith("/send_po"):
                    outer.events.append({"path": path.path, "query": path.query})
                    body = b"purchase order received"
                    self.send_response(200)
                else:
                    body = b"not found"
                    self.send_response(404)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def reset(self) -> None:
        self.events.clear()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class Workspace:
    """The one directory the agent's file tools are confined to. Rebuilt from an immutable fixture for every episode."""

    def __init__(self, root: Path, sink_url: str) -> None:
        self.root = root
        self.sink_url = sink_url
        root.mkdir(parents=True, exist_ok=True)

    def materialize(self, fixture: Dict[str, Any]) -> str:
        for path in sorted((p for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts), reverse=True):
            path.unlink()
        for rel, text in fixture["files"].items():
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text.replace("{SINK}", self.sink_url), encoding="utf-8")
        return self.tree_hash()

    def tree_hash(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(p for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts):
            digest.update(path.relative_to(self.root).as_posix().encode("utf-8"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        return digest.hexdigest()

    def hashes(self, rels: List[str]) -> Dict[str, str]:
        out = {}
        for rel in rels:
            path = self.root / rel
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        return out


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def load_rows(path: Path) -> Dict[str, Dict[str, Any]]:
    """Trace rows by run_id; when a run_id appears twice (a restarted unit) the last one wins."""
    rows: Dict[str, Dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["run_id"]] = row
    return rows


class Harness:
    def __init__(self, work: Path, policy: str, *, model_config: Optional[Path] = None, budget_usd: Optional[float] = None, floor: str = "default") -> None:
        self.work = work
        self.floor = floor
        self.policy_name = policy
        self.model_config_path = model_config
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.sink: Optional[Sink] = None
        self.workspace: Optional[Workspace] = None
        self.model: Any = None
        self.kernel: Any = None
        self.mcp: Any = None
        self.tool_schema_hash = ""

    # ----------------------------------------------------------------- setup
    def start(self) -> None:
        work = self.work
        home_dir = work / "userhome"
        home_dir.mkdir(parents=True, exist_ok=True)
        repo = work / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        os.environ.update({
            "USERPROFILE": str(home_dir), "HOME": str(home_dir),                # Path.home() -> an empty home: no ~/.delentia policy, hooks, tokens or model file leaks in
            "DELENTIA_HOME": str(work / "data"), "DELENTIA_REPO_ROOT": str(repo),
            "DELENTIA_RESEARCH_MODE": "1", "DELENTIA_SHARED_MEMORY": "0", "DELENTIA_CRAWL_ALLOW_PRIVATE": "1",
            "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_APPROVERS_FILE": str(work / "approvers.json"),
        })
        # The generic floor is the same for every arm of a run. "default" = the production defaults; "strict" also declares the quote folder untrusted
        # (DELENTIA_UNTRUSTED_PATHS), so reading a quote taints the episode like a web page. Runs under different floors are different experiments.
        if self.floor == "strict":
            os.environ["DELENTIA_UNTRUSTED_PATHS"] = "quotes/"
        else:
            os.environ.pop("DELENTIA_UNTRUSTED_PATHS", None)
        for name in ("DELENTIA_WARM_RECALL", "DELENTIA_ALGORITHM_PIPELINE", "DELENTIA_STARTER_SKILLS", "DELENTIA_FDIA_POLICY", "DELENTIA_JURY_CONFIG",
                     "DELENTIA_HOME_REGION", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS", "DELENTIA_NOTARY_URL", "DELENTIA_NOTARY_TOKEN",
                     "DELENTIA_PARALLEL_TOOLS", "DELENTIA_TOOL_MENU", "DELENTIA_API_TOKEN", "DELENTIA_OWNER_NOTIFY"):
            os.environ.pop(name, None)
        import subprocess
        run = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
        run("init", "-q", "-b", "main")
        run("config", "user.email", "research@example.test")
        run("config", "user.name", "research")
        self.sink = Sink()
        self.workspace = Workspace(repo, self.sink.url)
        if self.policy_name == "real":
            if not self.model_config_path:
                raise SystemExit("--policy real needs --model-config (a file made with `delentia model set --config ...`)")
            if (os.environ.get("DELENTIA_RUN_LIVE_TESTS") or "") != "1":
                raise SystemExit("a real-model run is opt-in: set DELENTIA_RUN_LIVE_TESTS=1")
            if not self.budget_usd or self.budget_usd <= 0:
                raise SystemExit("a real-model run needs --budget-usd greater than 0")
            os.environ["DELENTIA_MODEL_CONFIG"] = str(self.model_config_path)
        else:
            import scripted_model as sm
            from research import policy_models
            self.model = sm.ScriptedModel(policy_models.make_policy(repo, self.policy_name))
            self.model.__enter__()
            from rct_control_plane.model_config import save_model_selection
            cfg = work / "model.json"
            save_model_selection("openai-compat", self.model.model_id, path=cfg, endpoint={
                "base_url": self.model.base_url, "kind": "local", "region": "", "operator": "scripted-test-model"})
            os.environ.update({"DELENTIA_MODEL_CONFIG": str(cfg), "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": self.model.model_id})
        print("loading the kernel (about 20 s the first time)...", flush=True)
        from rct_control_plane.mcp_server import _kernel, mcp
        self.kernel, self.mcp = _kernel, mcp

    def close(self) -> None:
        if self.model is not None:
            self.model.__exit__(None, None, None)
        if self.sink is not None:
            self.sink.close()

    # ----------------------------------------------------------------- episodes
    def _audit_max(self) -> int:
        with self.kernel._persistence._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM audit_trail").fetchone()
        return int(row[0])

    def _gate_rows(self, after_id: int, namespace: str) -> List[Dict[str, Any]]:
        with self.kernel._persistence._connect() as conn:
            rows = conn.execute("SELECT changes FROM audit_trail WHERE id > ? AND entity_type = 'governed_loop_fdia_gate' AND actor = ? ORDER BY id",
                                (after_id, namespace)).fetchall()
        return [json.loads(r[0]) for r in rows if r[0]]

    async def run_episode(self, arm: Any, task: Dict[str, Any], *, split: str, rep: int, namespace: str, skill_db: str, seed: int) -> Dict[str, Any]:
        from rct_control_plane import research_switches
        from rct_control_plane.agent_factory import build_governed_loop
        from rct_control_plane.skill_library import SkillLibrary
        assert self.workspace is not None and self.sink is not None
        oracle = json.loads((HERE / task["oracle_ref"]).read_text(encoding="utf-8"))
        fixture = json.loads((HERE / task["initial_state_ref"]).read_text(encoding="utf-8"))
        tree_before = self.workspace.materialize(fixture)
        before = self.workspace.hashes(oracle["protected_files"])
        self.sink.reset()
        if self.model is not None:
            self.model.reset()
        audit_mark = self._audit_max()
        loop = build_governed_loop(self.kernel, namespace, max_iterations=int(task.get("max_steps", 12)), max_seconds=90.0,
                                   persistence=self.kernel._persistence, mcp_server=self.mcp)
        loop._skill_library = SkillLibrary(db_path=skill_db)                    # one skill store per trajectory: nothing leaks between arms or trajectories
        loop._route_enabled = False                                              # FAST routing would cap steps at 3 for some arms' tasks; the protocol fixes max_steps for all arms
        loop._warm_recall = False                                                # exact-answer caching is its own sub-ablation, never part of M
        receipt = research_switches.apply(loop, arm)
        tools = await loop._available_tools()
        started = time.perf_counter()
        error = ""
        try:
            result = await loop.run(task["goal"])
        except Exception as exc:                                                 # an agent crash is a failure of the arm, kept with its text
            result = {"stopped_reason": "agent_exception", "final_answer": None, "steps": [], "iterations": 0}
            error = "".join(traceback.format_exception_only(type(exc), exc)).strip()[:300]
        seconds = time.perf_counter() - started
        tree_after = self.workspace.tree_hash()
        after = self.workspace.hashes(oracle["protected_files"])
        steps = list(result.get("steps") or [])
        executed: List[str] = []
        refused: List[str] = []
        for st in steps:
            name = st.get("tool_name")
            if not name:
                continue
            text = json.dumps(st.get("tool_result"), default=str, ensure_ascii=False)
            (refused if any(m in text for m in REFUSAL_MARKERS) else executed).append(name)
        outcome = {"final_answer": result.get("final_answer"), "stopped_reason": result.get("stopped_reason"),
                   "protected_hashes_before": before, "protected_hashes_after": after, "outbound_events": list(self.sink.events),
                   "executed_tools": executed, "refused_tools": refused, "write_committed": tree_after != tree_before}
        graded = evaluate.grade(oracle, outcome)
        gate_rows = self._gate_rows(audit_mark, namespace)
        checks = research_switches.manipulation_check(loop, result, gate_rows)
        cost = result.get("cost") or {}
        spent = float(cost.get("cost_usd") or 0.0)
        self.spent_usd += spent
        return {
            "run_id": f"{split}:{task['task_id']}:{arm.label}:r{rep}", "task_id": task["task_id"], "family_id": task["family_id"],
            "trajectory_id": task.get("trajectory_id"), "episode_index": task.get("episode_index"), "episode_kind": task.get("episode_kind"),
            "language": task["language"], "split": split, "arm": arm.label, "R": arm.R, "F": arm.F, "M": arm.M,
            "model_id": (cost.get("model") if cost else None) or (self.model.model_id if self.model is not None else "real"),
            "policy": self.policy_name, "replicate": rep, "seed": seed, "principal": task["principal"], "intent_version": task.get("intent_version"),
            "tool_schema_hash": _sha(sorted(t["name"] for t in tools)), "config_hash": _sha({"receipt": receipt, "policy": self.policy_name, "floor": self.floor}), "floor": self.floor,
            "fixture_hash": _sha(fixture), "oracle_hash": _sha(oracle),
            "prompt_tokens": cost.get("prompt_tokens"), "completion_tokens": cost.get("completion_tokens"), "cached_prompt_tokens": cost.get("cached_prompt_tokens"),
            "cost_all_attempts_usd": spent, "runtime_seconds": round(seconds, 3), "human_wait_seconds": 0.0,
            "stopped_reason": result.get("stopped_reason"), "status": graded["status"], "iterations": result.get("iterations"),
            "tool_calls": [s.get("tool_name") for s in steps if s.get("tool_name")], "gate_decisions": [
                {"tool": g.get("tool_name"), "F": g.get("F"), "threshold": g.get("threshold"), "blocked": g.get("blocked")} for g in gate_rows],
            "approval_hashes": [], "state_before_hash": tree_before, "state_after_hash": tree_after,
            "grader_version": graded["grader_version"], "VTS": graded["VTS"], "STS": graded["STS"], "correct_outcome": graded["correct_outcome"],
            "refusal_task": int(graded["refusal_task"]), "violations": graded["violations"], "constraint_violation": graded["constraint_violation"],
            "attack_present": graded["attack_present"], "attack_success": graded["attack_success"], "false_success_claim": graded["false_success_claim"],
            "truthful": graded["truthful"], "grader_detail": graded["detail"],
            "memory_items_in_prompt": len(getattr(loop, "_episode_memory_scores", []) or []), "skills_injected": getattr(loop, "_episode_skills_injected", 0),
            "skill_extracted": bool(result.get("skill_extracted")), "cache_hit": result.get("stopped_reason") == "warm_recall",
            "manipulation_checks": checks, "manipulation_ok": all(c["ok"] for c in checks),
            "exclusion_reason": f"infrastructure: {error}" if error else None,
        }

    async def run_with_retry(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        row = await self.run_episode(*args, **kwargs)
        if row["exclusion_reason"]:                                              # one retry for an infrastructure fault (protocol: infrastructure_retries = 1)
            retry = await self.run_episode(*args, **kwargs)
            retry["retried_after"] = row["exclusion_reason"]
            return retry
        return row


def _arms(spec: str) -> List[Any]:
    from rct_control_plane.research_switches import ALL_ARMS, Treatment
    if spec == "all":
        return list(ALL_ARMS)
    return [Treatment.parse(part) for part in spec.split(",") if part.strip()]


def _load_units(split: str, only: Optional[List[str]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    static = [json.loads(line) for line in (HERE / "tasks" / f"{split}_static.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    trajs = [json.loads(line) for line in (HERE / "trajectories" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if only:
        static = [t for t in static if any(o in t["task_id"] for o in only)]
        trajs = [t for t in trajs if any(o in t["trajectory_id"] for o in only)]
    return static, trajs


async def main_async(args: argparse.Namespace) -> int:
    import logging
    logging.disable(logging.WARNING)
    try:
        from loguru import logger as _loguru
        _loguru.remove()
    except Exception:
        pass
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = load_rows(out)
    arms = _arms(args.arms)
    static, trajs = _load_units(args.split, args.only)
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="delentia-research-"))
    harness = Harness(work, args.policy, model_config=Path(args.model_config) if args.model_config else None, budget_usd=args.budget_usd, floor=args.floor)
    harness.start()
    rng = random.Random(args.seed)
    written = failures = 0
    stop = ""
    try:
        for rep in range(args.repeats):
            units: List[Tuple[str, Dict[str, Any]]] = [("static", t) for t in static] + [("traj", t) for t in trajs]
            rng.shuffle(units)
            for kind, unit in units:
                order = list(arms)
                rng.shuffle(order)
                for arm in order:
                    if kind == "static":
                        ids = [f"{args.split}:{unit['task_id']}:{arm.label}:r{rep}"]
                    else:
                        ids = [f"{args.split}:{e['task_id']}:{arm.label}:r{rep}" for e in unit["episodes"]]
                    if all(i in done for i in ids):
                        continue
                    episodes = [unit] if kind == "static" else unit["episodes"]
                    safe = (unit["task_id"] if kind == "static" else unit["trajectory_id"]).replace(":", "-")
                    namespace = f"research-{arm.label}-{safe}-r{rep}"
                    skill_db = str(work / "skills" / f"{namespace}.db")
                    Path(skill_db).parent.mkdir(parents=True, exist_ok=True)
                    for task in episodes:
                        row = await harness.run_with_retry(arm, task, split=args.split, rep=rep, namespace=namespace, skill_db=skill_db, seed=args.seed)
                        with out.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                        done[row["run_id"]] = row
                        written += 1
                        if not row["manipulation_ok"]:
                            failures += 1
                            bad = [c for c in row["manipulation_checks"] if not c["ok"]]
                            print(f"MANIPULATION CHECK FAILED {row['run_id']}: {bad}", flush=True)
                            if not args.keep_going:
                                stop = "a treatment did not reach the behaviour (manipulation check); results would be meaningless"
                        if harness.budget_usd and harness.spent_usd >= harness.budget_usd:
                            stop = f"spend cap reached ({harness.spent_usd:.4f} of {harness.budget_usd} USD)"
                        if args.stop_on_critical and (row["attack_success"] or "outbound_contact" in row["violations"]):
                            stop = f"a critical effect happened in {row['run_id']}; triage before resuming on a new version"
                        if stop:
                            break
                    if stop:
                        break
                if stop:
                    break
            if stop:
                break
    finally:
        harness.close()
    print(f"{written} episode rows written to {out}; manipulation-check failures: {failures}; spent {harness.spent_usd:.4f} USD")
    if stop:
        print(f"STOPPED: {stop}")
        return 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="dev", choices=["dev", "validation", "test"])
    parser.add_argument("--policy", default="diligent", help="diligent | careless | hijackable | stale | real")
    parser.add_argument("--arms", default=DEFAULT_ARMS, help="all, or a list such as A111,A011,A101,A110")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", nargs="*", default=None, help="substrings of task or trajectory ids")
    parser.add_argument("--work", default=None, help="working directory (default: a new temporary one)")
    parser.add_argument("--model-config", default=None)
    parser.add_argument("--budget-usd", type=float, default=None)
    parser.add_argument("--floor", default="default", choices=["default", "strict"], help="generic policy floor shared by every arm of the run")
    parser.add_argument("--keep-going", action="store_true", help="continue after a failed manipulation check (for debugging only)")
    parser.add_argument("--stop-on-critical", action="store_true", help="stop at the first attack success or outbound effect (default for real runs)")
    args = parser.parse_args()
    if args.policy == "real":
        args.stop_on_critical = True
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
