"""
Round 55 (criterion T7): does the system get cheaper and faster when it meets the same goal again?

Each goal is run twice for the same person in one data home, with warm recall on (a verified answer is re-used without a model call
when the read-only evidence it rested on is unchanged) and skills on. Reports, per goal, the model calls and tokens of the first and the
second run, and whether both answers were right. The criterion (T7 of the full-test plan): the second run uses at least 20% fewer model
calls, with the answer still right.

    python scripts/measure_repeat_goal.py qwen2.5:7b --provider ollama
    python scripts/measure_repeat_goal.py some/model --provider openrouter --price-in 0.2 --price-out 0.8     (spends money; needs the opt-in)

The goals use a small temporary repository, so the evidence they rest on really is unchanged between the two runs, and a goal that
touches something changing in between would (correctly) not be answered warm.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

GOALS: List[Dict[str, Any]] = [
    {"name": "project name", "goal": "Read the file pyproject.toml and tell me the project name", "expect": ["sample-service"]},
    {"name": "readme title", "goal": "Read the file README.md and tell me its title", "expect": ["Sample service"]},
    {"name": "release manager", "goal": "Read the file docs/notes.md and tell me who the release manager is", "expect": ["Somchai"]},
]


async def run(model: str, provider: str, max_iterations: int, max_seconds: float) -> Dict[str, Any]:
    import full_pipeline_cases as f
    work = Path(tempfile.mkdtemp(prefix="delentia-repeat-"))
    env = f.Env(work)
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(env.repo), "DELENTIA_MODEL_CONFIG": str(work / "model.json"),
                       "DELENTIA_LLM_PROVIDER": provider, "DELENTIA_LLM_MODEL": model, "DELENTIA_WARM_RECALL": "1"})
    os.environ.pop("DELENTIA_PARALLEL_TOOLS", None)
    env.build_repo()
    from rct_control_plane.mcp_server import _kernel, mcp
    env.kernel, env.mcp = _kernel, mcp
    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(GOALS):
        namespace = f"repeat-{index}"
        runs = []
        for _attempt in (1, 2):
            loop = env.loop(namespace, max_iterations=max_iterations, max_seconds=max_seconds)
            try:
                result = await loop.run(item["goal"])
                error = None
            except Exception as exc:                          # noqa: BLE001 - recorded, not hidden
                result, error = {"final_answer": None, "cost": {}, "stopped_reason": "exception"}, f"{type(exc).__name__}: {exc}"[:150]
            cost = result.get("cost") or {}
            answer = str(result.get("final_answer") or "")
            runs.append({"calls": cost.get("calls") or 0, "prompt_tokens": cost.get("prompt_tokens") or 0, "completion_tokens": cost.get("completion_tokens") or 0,
                         "correct": all(t.lower() in answer.lower() for t in item["expect"]), "stopped": result.get("stopped_reason"), "error": error})
        rows.append({"goal": item["name"], "first": runs[0], "second": runs[1]})
        print(f"  {item['name']:<16} first: {runs[0]['calls']} calls ok={runs[0]['correct']} | second: {runs[1]['calls']} calls ok={runs[1]['correct']}", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    return {"goals": rows, "summary": summarise(rows)}


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Median reduction in model calls and in tokens from the first run to the second, over the goals whose first run was right."""
    usable = [r for r in rows if r["first"]["correct"] and r["first"]["calls"] > 0]

    def drop(key: str) -> float:
        values = []
        for r in usable:
            first = r["first"][key] if key == "calls" else r["first"]["prompt_tokens"] + r["first"]["completion_tokens"]
            second = r["second"][key] if key == "calls" else r["second"]["prompt_tokens"] + r["second"]["completion_tokens"]
            values.append(1 - second / first if first else 0.0)
        return round(statistics.median(values), 3) if values else 0.0

    return {"goals": len(rows), "usable": len(usable), "second_run_still_correct": sum(1 for r in usable if r["second"]["correct"]),
            "median_call_reduction": drop("calls"), "median_token_reduction": drop("tokens")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model")
    parser.add_argument("--provider", choices=["ollama", "openrouter"], default="ollama")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--max-seconds", type=float, default=300.0)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    if args.provider == "openrouter" and (not os.environ.get("OPENROUTER_API_KEY") or os.environ.get("DELENTIA_RUN_LIVE_TESTS") != "1"):
        raise SystemExit("--provider openrouter spends money: set OPENROUTER_API_KEY and DELENTIA_RUN_LIVE_TESTS=1 first")
    import logging
    logging.disable(logging.WARNING)
    try:
        from loguru import logger as _loguru
        _loguru.remove()
    except Exception:
        pass
    out = asyncio.run(run(args.model, args.provider, args.max_iterations, args.max_seconds))
    text = json.dumps({args.model: out}, indent=2)
    print(json.dumps(out["summary"]))
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
