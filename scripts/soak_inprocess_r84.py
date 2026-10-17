"""
Round 84: an in-process soak at zero cost. N governed episodes in ONE process against a fake OpenRouter on loopback, with the experiment budget guard in front, measuring what a long paid run
would suffer from: memory growth, open handles, time per episode drifting upwards, database growth, a ledger that drifts away from what the endpoint charged, and an audit chain that no longer
verifies after thousands of rows.

    python scripts/soak_inprocess_r84.py --episodes 300 --out soak.json

This is NOT the host soak of the research plan (1 h / 8-12 h / 72 h / 7 d on the machine that will run for real, with restarts and a clock). It runs a few minutes and catches the cheap
defects first. A model here is a script: nothing it says is about any real model.
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--every", type=int, default=25)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    import psutil
    import scripted_model as sm
    from fake_openrouter import FakeOpenRouter

    from research.daaes import delentia_session as ds
    from research.daaes.budget_guard import BudgetPolicy, ExperimentLedger
    from research.daaes.live_adapter import guarded, openrouter_provider

    home = Path(tempfile.mkdtemp(prefix="delentia-soak-"))
    os.environ.update({"DELENTIA_HOME": str(home), "OPENROUTER_API_KEY": "rehearsal-not-a-real-key", "DELENTIA_LLM_PROVIDER": "openrouter", "DELENTIA_LLM_MODEL": "rehearsal/model",
                       "DELENTIA_MEMORY_EMBED": "off", "DELENTIA_MEMORY_KEYS_DIR": str(home / "memkeys")})
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS"):
        os.environ.pop(name, None)
    proc = psutil.Process()

    def policy(req):
        if req.history_empty:
            return sm._call("delentia_read_repo_file", {"relative_path": "docs/a.md"}, "read")
        return sm._finish("The file says A.")

    samples = []
    seconds = []
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence

    with FakeOpenRouter({"rehearsal/model": {"in": 0.2, "out": 0.8}}, policy=policy) as server:
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = server.base_url
        budget = BudgetPolicy(total_usd=50.0, reserve_usd=1.0, max_cost_per_run_usd=1.0, max_llm_calls_per_run=10)
        ledger_path = home / "ledger.json"
        persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
        for n in range(1, args.episodes + 1):
            t = time.perf_counter()
            provider = guarded(openrouter_provider("rehearsal/model", base_url=server.base_url), ledger_path, budget, f"soak-{n}", 0.2, 0.8)
            with ds.data_home(home):
                loop = build_governed_loop(ds.NullKernel(), namespace=f"soak-{n % 5}", max_iterations=4, persistence=persistence, mcp_server=ds.ScriptedWorld(ds.FILES), conversation_turns=0, llm_provider=provider)
                result = asyncio.run(loop.run("Read docs/a.md and tell me what it says"))
            seconds.append(time.perf_counter() - t)
            if result.get("stopped_reason") != "llm_finished":
                print(f"episode {n} did not finish: {result.get('stopped_reason')}", file=sys.stderr)
            if n % args.every == 0 or n == args.episodes:
                gc.collect()
                db = (home / "agentic.db").stat().st_size if (home / "agentic.db").exists() else 0
                samples.append({"episode": n, "rss_mb": round(proc.memory_info().rss / 1e6, 1), "handles": proc.num_handles() if hasattr(proc, "num_handles") else proc.num_fds(),
                                "threads": proc.num_threads(), "db_mb": round(db / 1e6, 2), "sec_per_episode_window": round(sum(seconds[-args.every:]) / len(seconds[-args.every:]), 3)})
                print(json.dumps(samples[-1]), flush=True)
        led = ExperimentLedger(ledger_path, budget)
        from rct_control_plane.audit_chain import verify_audit_chain
        t = time.perf_counter()
        report = verify_audit_chain(sqlite3.connect(str(home / "agentic.db")))
        verify_s = round(time.perf_counter() - t, 2)
        rows = sqlite3.connect(str(home / "agentic.db")).execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0]
        summary = {"episodes": args.episodes, "endpoint_calls": server.calls, "endpoint_spent_usd": round(server.spent, 6), "ledger_spent_usd": round(led.state["spent_usd"], 6),
                   "ledger_reserved_usd": round(led.state["reserved_usd"], 6), "audit_rows": rows, "audit_chain_ok": bool(getattr(report, "ok", False)), "audit_verify_seconds": verify_s,
                   "rss_first_mb": samples[0]["rss_mb"], "rss_last_mb": samples[-1]["rss_mb"], "handles_first": samples[0]["handles"], "handles_last": samples[-1]["handles"],
                   "sec_first_window": samples[0]["sec_per_episode_window"], "sec_last_window": samples[-1]["sec_per_episode_window"], "samples": samples}
    print(json.dumps({k: v for k, v in summary.items() if k != "samples"}, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
