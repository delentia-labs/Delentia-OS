"""
Round 106: the cost and size criteria W2 and W3 of research/DELTA_STATE_LOG_CRITERIA_R106.md, measured.

W2  200 real governed episodes (scripted model, real loop, real SQLite) in pairs: the same episode with the state log on and with it off, the order alternating so a warming machine favours neither.
    The cost is the median and the 95th percentile of the paired difference.
W3  1,000 episodes written for one person (the summaries, without the model, so the run is about the log): bytes per episode, and the time verify() takes.

Run:  python -m research.measure_state_log_r106 [--episodes 200] [--out research/results_round106/state_log.json]
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import rct_control_plane.autonomous_loop as autonomous_loop_module  # noqa: E402
from rct_control_plane import agent_state_log  # noqa: E402
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41  # noqa: E402
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop  # noqa: E402
from rct_control_plane.persistence import ControlPlanePersistence  # noqa: E402
from rct_control_plane.skill_library import SkillLibrary  # noqa: E402


class _Tool:
    def __init__(self, name):
        self.name, self.description, self.input_schema = name, name, {}


class _Result:
    def __init__(self, payload):
        self.content = [type("C", (), {"text": json.dumps(payload)})()]


class World:
    async def list_tools(self):
        return [_Tool("delentia_read_repo_file"), _Tool("delentia_recall")]

    async def call_tool(self, name, args):
        return _Result({"content": 'name = "delentia-os"', "path": args.get("relative_path")})


async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
    if not history:
        return {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}, "reasoning": "read it", "final_answer": None}
    return {"action": "finish", "reasoning": "done", "final_answer": "The project name is delentia-os.", "tool_name": None, "tool_args": {}}


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def paired_cost(episodes: int, control: bool = False) -> dict:
    autonomous_loop_module.decide_next_action = fake
    kernel = AlgorithmKernel41()
    diffs, on_times, off_times = [], [], []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        persistence = ControlPlanePersistence(db_path=str(Path(tmp) / "agentic.db"))
        skills = SkillLibrary(db_path=str(Path(tmp) / "skills.db"))

        def one(on: bool) -> float:
            os.environ[agent_state_log.ENV] = "on" if (on and not control) else "off"   # control: both sides are OFF, so any difference is the machine's noise
            loop = GovernedAutonomousLoop(mcp_server=World(), persistence=persistence, kernel=kernel, skill_library=skills, max_iterations=4, namespace="measure")
            t = time.perf_counter()
            result = asyncio.run(loop.run("Read the file pyproject.toml and tell me the project name"))
            dt = (time.perf_counter() - t) * 1000.0
            assert result["stopped_reason"] == "llm_finished"
            if on and not control:
                assert "version" in result["state_log"], result["state_log"]
            return dt

        for _ in range(3):                                   # warm-up, not counted
            one(True), one(False)
        for i in range(episodes):
            first_on = i % 2 == 0
            a = one(first_on)
            b = one(not first_on)
            on, off = (a, b) if first_on else (b, a)
            on_times.append(on)
            off_times.append(off)
            diffs.append(on - off)
        agent_state_log.close_all()
    return {"episodes": episodes, "median_added_ms": round(statistics.median(diffs), 2), "p95_added_ms": round(percentile(diffs, 0.95), 2),
            "median_episode_off_ms": round(statistics.median(off_times), 1), "median_episode_on_ms": round(statistics.median(on_times), 1)}


def size_and_verify(episodes: int = 1000) -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        persistence = ControlPlanePersistence(db_path=str(Path(tmp) / "agentic.db"))
        log = agent_state_log.AgentStateLog(Path(tmp) / "one.db", "one")
        reasons = ["llm_finished", "llm_finished", "llm_finished", "pending_approval", "fdia_blocked", "max_iterations_reached"]
        t = time.perf_counter()
        for i in range(episodes):
            log.record_episode({"episode_id": f"ep-{i:06d}", "stopped_reason": reasons[i % len(reasons)], "iterations": 2 + i % 3, "verified": i % 4 != 3, "tool_calls": 1 + i % 3,
                                "cost_usd": 0.0003 * (1 + i % 5), "growth_G": 1.0 + i / 5000.0, "memory": {"events": i // 3, "head_hash": f"{i:064x}"}, "skills": i // 20,
                                "audit": {"seq": i * 7, "row_hash": f"{i * 7:064x}"}}, persistence)
        write_s = time.perf_counter() - t
        log.close()
        reopened = agent_state_log.AgentStateLog(Path(tmp) / "one.db", "one")
        t = time.perf_counter()
        report = reopened.verify(persistence)
        verify_s = time.perf_counter() - t
        size = (Path(tmp) / "one.db").stat().st_size
        sizes = reopened.log.sizes()
        reopened.close()
    return {"episodes": episodes, "file_bytes": size, "bytes_per_episode": round(size / episodes, 1), "delta_plus_snapshot_bytes": sizes["total_bytes"], "write_ms_per_episode": round(write_s * 1000 / episodes, 2),
            "verify_seconds": round(verify_s, 3), "verify_ok": report["ok"], "anchors": report["anchors"]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=200)
    ap.add_argument("--control", action="store_true", help="off against off: the noise floor of the paired difference")
    ap.add_argument("--out", default=str(Path(__file__).with_name("results_round106") / "state_log.json"))
    args = ap.parse_args(argv)
    os.environ.setdefault("DELENTIA_STATE_LOG_ANCHOR_EVERY", "25")
    if args.control:
        out = paired_cost(args.episodes, control=True)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).with_name("state_log_control.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(json.dumps(out, indent=1))
        return 0
    result = {"w2_cost": paired_cost(args.episodes), "w3_size": size_and_verify()}
    w2, w3 = result["w2_cost"], result["w3_size"]
    result["rules"] = {"W2_median_le_15ms": w2["median_added_ms"] <= 15, "W2_p95_le_40ms": w2["p95_added_ms"] <= 40,
                       "W3_le_1500_bytes_per_episode": w3["bytes_per_episode"] <= 1500, "W3_verify_le_2s": w3["verify_seconds"] <= 2.0 and w3["verify_ok"]}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0 if all(result["rules"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
