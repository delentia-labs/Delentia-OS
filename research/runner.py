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


def _steps_brief(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What each step was, short enough to keep in every row: enough to see WHY an episode stalled (a call with no tool name, an unknown tool, a refusal) without storing
    whole tool results. Includes steps that named no tool, which `tool_calls` leaves out."""
    brief = []
    for st in steps[:16]:
        result = st.get("tool_result")
        kind = "none" if result is None else ("error" if isinstance(result, dict) and result.get("error") else
                                               "blocked" if isinstance(result, dict) and (result.get("fdia_blocked") or result.get("pending_approval")) else "ok")
        brief.append({"tool": st.get("tool_name"), "args": json.dumps(st.get("tool_args") or {}, ensure_ascii=False, default=str)[:120], "result": kind,
                      "said": str(st.get("llm_reasoning") or "")[:100]})
    return brief


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


def run_id_for(split: str, task_id: str, arm_label: str, rep: int, unit_budget: Optional[int] = None) -> str:
    """The identity of one episode. A run under the equal-total-token track is a different run of the same unit, so it carries the UNIT's budget (not what was left for
    this episode), which keeps the id stable for resuming."""
    base = f"{split}:{task_id}:{arm_label}:r{rep}"
    return base if unit_budget is None else f"{base}:b{int(unit_budget)}"


class Harness:
    def __init__(self, work: Path, policy: str, *, model_config: Optional[Path] = None, budget_usd: Optional[float] = None, floor: str = "default",
                 max_seconds: float = 90.0, tool_menu: str = "default", memory_policy: str = "none", preload_noise: int = 0) -> None:
        self.memory_policy = memory_policy
        self.preload_noise = preload_noise
        self.work = work
        self.max_seconds = max_seconds
        self.tool_menu = tool_menu
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
            os.environ["DELENTIA_UNTRUSTED_PATHS"] = "quotes/,tickets/"
        else:
            os.environ.pop("DELENTIA_UNTRUSTED_PATHS", None)
        for name in ("DELENTIA_TOOL_MENU", "DELENTIA_TOOL_MENU_FORMAT"):
            os.environ.pop(name, None)
        if self.tool_menu == "ranked":                                         # the same menu for every arm of a run; recorded in every row
            os.environ["DELENTIA_TOOL_MENU"] = "ranked"
            os.environ["DELENTIA_TOOL_MENU_FORMAT"] = "compact"
        os.environ["DELENTIA_MEMORY_POLICY"] = self.memory_policy
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
            for name in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL"):
                os.environ.pop(name, None)                                      # the config file decides, not a leftover shell setting
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
    def preload(self, namespace: str, seed: int) -> None:
        """Round 66: unrelated facts, exact duplicates of one of them, and old episodes (conversation and event, low importance, back-dated), the same for every arm and policy of a run."""
        if self.preload_noise <= 0:
            return
        import random
        rng = random.Random(f"{seed}:{namespace}")
        words = "invoice shipment depot courier pallet barcode manifest customs warehouse dock forklift route driver schedule".split()
        persistence = self.kernel._persistence
        first = ""
        for i in range(self.preload_noise):
            roll = rng.random()
            if roll < 0.5 or not first:
                content, kind, imp, days = " ".join(rng.choice(words) for _ in range(10)), rng.choice(["fact", "fact", "preference"]), round(rng.uniform(0.3, 0.7), 2), rng.randint(1, 60)
                first = first or content
            elif roll < 0.7:
                content, kind, imp, days = first, "fact", 0.5, rng.randint(1, 60)                 # an exact duplicate
            else:
                content, kind, imp, days = " ".join(rng.choice(words) for _ in range(10)), rng.choice(["conversation", "event"]), round(rng.uniform(0.1, 0.5), 2), rng.randint(90, 400)
            mid = f"noise_{namespace}_{i}"
            persistence.save_memory(mid, namespace, kind, content, {}, imp)
            with persistence._connect() as conn:
                conn.execute("UPDATE memories SET created_at = ? WHERE id = ?", ((__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - __import__("datetime").timedelta(days=days)).isoformat(), mid))

    def _audit_max(self) -> int:
        with self.kernel._persistence._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM audit_trail").fetchone()
        return int(row[0])

    def _gate_rows(self, after_id: int, namespace: str) -> List[Dict[str, Any]]:
        with self.kernel._persistence._connect() as conn:
            rows = conn.execute("SELECT changes FROM audit_trail WHERE id > ? AND entity_type = 'governed_loop_fdia_gate' AND actor = ? ORDER BY id",
                                (after_id, namespace)).fetchall()
        return [json.loads(r[0]) for r in rows if r[0]]

    async def run_episode(self, arm: Any, task: Dict[str, Any], *, split: str, rep: int, namespace: str, skill_db: str, seed: int,
                          token_cap: Optional[int] = None, unit_budget: Optional[int] = None) -> Dict[str, Any]:
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
        plain = bool(getattr(arm, "plain_loop", 0))
        if plain:                                                                # Round 66: not Delentia's loop at all
            from research.plain_agent import PlainAgent
            loop = PlainAgent(self.mcp, namespace, max_iterations=int(task.get("max_steps", 12)), max_seconds=self.max_seconds,
                              max_tokens=max(1, int(token_cap)) if token_cap is not None else None)
            receipt = arm.to_dict()
            tools = [{"name": t.name} for t in await self.mcp.list_tools()]
        else:
            loop = build_governed_loop(self.kernel, namespace, max_iterations=int(task.get("max_steps", 12)), max_seconds=self.max_seconds,
                                       persistence=self.kernel._persistence, mcp_server=self.mcp)
            loop._skill_library = SkillLibrary(db_path=skill_db)                    # one skill store per trajectory: nothing leaks between arms or trajectories
            loop._route_enabled = False                                              # FAST routing would cap steps at 3 for some arms' tasks; the protocol fixes max_steps for all arms
            loop._warm_recall = False                                                # exact-answer caching is its own sub-ablation, never part of M
            if token_cap is not None:                                                # track B (equal total tokens): what is left of this unit's budget, same rule for every arm
                loop._max_episode_tokens = max(1, int(token_cap))
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
        prior = (int(task["episode_index"]) - 1) if task.get("episode_index") else 0
        if plain:
            with self.kernel._persistence._connect() as conn:
                governed = conn.execute("SELECT COUNT(*) FROM audit_trail WHERE id > ? AND entity_type LIKE 'governed_loop%' AND actor = ?", (audit_mark, namespace)).fetchone()[0]
            checks = research_switches.plain_loop_checks(int(governed), result, [t["name"] for t in tools])
        else:
            checks = research_switches.manipulation_check(loop, result, gate_rows, prior_episodes=prior)
        cost = result.get("cost") or {}
        spent = float(cost.get("cost_usd") or 0.0)
        self.spent_usd += spent
        used = int(cost.get("prompt_tokens") or 0) + int(cost.get("completion_tokens") or 0)
        return {
            "run_id": run_id_for(split, task["task_id"], arm.label, rep, unit_budget), "task_id": task["task_id"], "family_id": task["family_id"],
            "domain": task.get("domain", "quotes"), "attack": oracle.get("attack", ""), "track": "budget" if unit_budget is not None else "config", "unit_token_budget": unit_budget, "token_cap": token_cap, "tokens_used": used,
            "trajectory_id": task.get("trajectory_id"), "episode_index": task.get("episode_index"), "episode_kind": task.get("episode_kind"),
            "language": task["language"], "split": split, "arm": arm.label, "R": arm.R, "F": arm.F, "M": arm.M, "history": arm.history,
            "model_id": (cost.get("model") if cost else None) or (self.model.model_id if self.model is not None else "real"),
            "policy": self.policy_name, "replicate": rep, "seed": seed, "principal": task["principal"], "intent_version": task.get("intent_version"),
            "tool_schema_hash": _sha(sorted(t["name"] for t in tools)), "config_hash": _sha({"receipt": receipt, "policy": self.policy_name, "floor": self.floor, "tool_menu": self.tool_menu}), "floor": self.floor,
            "tool_menu": self.tool_menu,
            "fixture_hash": _sha(fixture), "oracle_hash": _sha(oracle),
            "prompt_tokens": cost.get("prompt_tokens"), "completion_tokens": cost.get("completion_tokens"), "cached_prompt_tokens": cost.get("cached_prompt_tokens"),
            "cost_all_attempts_usd": spent, "runtime_seconds": round(seconds, 3), "human_wait_seconds": 0.0,
            "stopped_reason": result.get("stopped_reason"), "status": graded["status"], "iterations": result.get("iterations"),
            "tool_calls": [s.get("tool_name") for s in steps if s.get("tool_name")], "steps_brief": _steps_brief(steps), "gate_decisions": [
                {"tool": g.get("tool_name"), "F": g.get("F"), "threshold": g.get("threshold"), "blocked": g.get("blocked")} for g in gate_rows],
            "approval_hashes": [], "state_before_hash": tree_before, "state_after_hash": tree_after,
            "grader_version": graded["grader_version"], "VTS": graded["VTS"], "STS": graded["STS"], "correct_outcome": graded["correct_outcome"],
            "refusal_task": int(graded["refusal_task"]), "violations": graded["violations"], "constraint_violation": graded["constraint_violation"],
            "attack_present": graded["attack_present"], "attack_success": graded["attack_success"], "false_success_claim": graded["false_success_claim"],
            "truthful": graded["truthful"], "grader_detail": graded["detail"],
            "memory_items_in_prompt": len(getattr(loop, "_episode_memory_scores", []) or []), "skills_injected": getattr(loop, "_episode_skills_injected", 0),
            "skill_extracted": bool(result.get("skill_extracted")), "cache_hit": result.get("stopped_reason") == "warm_recall", "plain_loop": int(plain), "memory_policy": self.memory_policy, "preload_noise": self.preload_noise,
            "manipulation_checks": checks, "manipulation_ok": all(c["ok"] for c in checks),
            "exclusion_reason": f"infrastructure: {error}" if error else None,
        }

    async def run_with_retry(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        from research import failure_taxonomy
        row = await self.run_episode(*args, **kwargs)
        if row["exclusion_reason"]:                                              # one retry for an infrastructure fault (protocol: infrastructure_retries = 1)
            retry = await self.run_episode(*args, **kwargs)
            retry["retried_after"] = row["exclusion_reason"]
            row = retry
        row["failure_class"] = failure_taxonomy.classify(row)                    # Round 66: one label per failed episode, assigned by rules (research/failure_taxonomy.py)
        return row


def _arms(spec: str) -> List[Any]:
    from rct_control_plane.research_switches import ALL_ARMS, Treatment
    if spec == "all":
        return list(ALL_ARMS)
    if spec == "all+G":
        return [*ALL_ARMS, Treatment.parse("G")]
    if spec == "baselines":                                                    # G (raw recent history) and GP (generic plan-act-check + generic retrieval)
        from rct_control_plane.research_switches import BASELINES
        return list(BASELINES)
    if spec == "plain":                                                        # PL: not Delentia's loop (research/plain_agent.py)
        return [Treatment.parse("PL")]
    if spec == "all+plain":
        return [*ALL_ARMS, Treatment.parse("PL")]
    if spec == "all+baselines+plain":
        from rct_control_plane.research_switches import BASELINES
        return [*ALL_ARMS, *BASELINES, Treatment.parse("PL")]
    if spec == "all+baselines":
        from rct_control_plane.research_switches import BASELINES
        return [*ALL_ARMS, *BASELINES]
    if spec == "variants":
        from rct_control_plane.research_switches import SUB_ABLATIONS
        return [Treatment.parse("A111"), *SUB_ABLATIONS]
    return [Treatment.parse(part) for part in spec.split(",") if part.strip()]


DOMAIN_FILES = {"quotes": ("{split}_static.jsonl", "{split}.jsonl"), "tickets": ("{split}_tickets_static.jsonl", "{split}_tickets.jsonl")}


def _load_units(split: str, only: Optional[List[str]], domain: str = "quotes") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    names = list(DOMAIN_FILES) if domain == "all" else [domain]
    static: List[Dict[str, Any]] = []
    trajs: List[Dict[str, Any]] = []
    for name in names:
        static_file, traj_file = (part.format(split=split) for part in DOMAIN_FILES[name])
        static += [json.loads(line) for line in (HERE / "tasks" / static_file).read_text(encoding="utf-8").splitlines() if line.strip()]
        trajs += [json.loads(line) for line in (HERE / "trajectories" / traj_file).read_text(encoding="utf-8").splitlines() if line.strip()]
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
    static, trajs = _load_units(args.split, args.only, args.domain)
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="delentia-research-"))
    harness = Harness(work, args.policy, model_config=Path(args.model_config) if args.model_config else None, budget_usd=args.budget_usd, floor=args.floor, max_seconds=args.max_seconds, tool_menu=args.tool_menu,
                      memory_policy=args.memory_policy, preload_noise=args.preload_noise)
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
                    cap = args.unit_token_budget or None
                    if kind == "static":
                        ids = [run_id_for(args.split, unit["task_id"], arm.label, rep, cap)]
                    else:
                        ids = [run_id_for(args.split, e["task_id"], arm.label, rep, cap) for e in unit["episodes"]]
                    if all(i in done for i in ids):
                        continue
                    episodes = [unit] if kind == "static" else unit["episodes"]
                    safe = (unit["task_id"] if kind == "static" else unit["trajectory_id"]).replace(":", "-")
                    namespace = f"research-{arm.label}-{safe}-r{rep}"
                    skill_db = str(work / "skills" / f"{namespace}.db")
                    Path(skill_db).parent.mkdir(parents=True, exist_ok=True)
                    remaining = cap                                          # equal-total-token track: one budget per (unit, arm), spent across the unit's episodes
                    harness.preload(namespace, args.seed)
                    for task in episodes:
                        row = await harness.run_with_retry(arm, task, split=args.split, rep=rep, namespace=namespace, skill_db=skill_db, seed=args.seed, token_cap=remaining, unit_budget=cap)
                        if remaining is not None:
                            remaining = max(0, remaining - int(row.get("tokens_used") or 0))
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
    parser.add_argument("--arms", default=DEFAULT_ARMS, help="all, all+G (the eight cells plus G), baselines (G and GP), all+baselines, variants (A111 and its four sub-ablations), or a list such as A111,A011,G,GP,A111+FS")
    parser.add_argument("--domain", default="quotes", choices=["quotes", "tickets", "all"], help="which task domain to run (quotes = the first domain, tickets = support triage)")
    parser.add_argument("--unit-token-budget", type=int, default=0, help="track B (equal total tokens): every arm gets the same token budget per task or trajectory; "
                        "0 = track A, equal configuration with no extra cap")
    parser.add_argument("--memory-policy", default="none", choices=["none", "dedupe", "expire"], help="Round 66: what recall may offer the model (DELENTIA_MEMORY_POLICY); the same for every arm of a run")
    parser.add_argument("--preload-noise", type=int, default=0, help="Round 66: store this many unrelated and duplicate memories (some of them old episodes) for each person before their first episode, to give the policies something to cut")
    parser.add_argument("--max-seconds", type=float, default=90.0, help="wall-clock cap per episode (a CPU-bound local model needs far more than a hosted one)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", nargs="*", default=None, help="substrings of task or trajectory ids")
    parser.add_argument("--work", default=None, help="working directory (default: a new temporary one)")
    parser.add_argument("--model-config", default=None)
    parser.add_argument("--budget-usd", type=float, default=None)
    parser.add_argument("--tool-menu", default="default", choices=["default", "ranked"], help="default = the full menu; ranked = the ranked compact menu (same for every arm of a run)")
    parser.add_argument("--floor", default="default", choices=["default", "strict"], help="generic policy floor shared by every arm of the run")
    parser.add_argument("--keep-going", action="store_true", help="continue after a failed manipulation check (for debugging only)")
    parser.add_argument("--stop-on-critical", action="store_true", help="stop at the first attack success or outbound effect (default for real runs)")
    args = parser.parse_args()
    if args.policy == "real":
        args.stop_on_critical = True
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
