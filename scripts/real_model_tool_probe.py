"""
Round 52: can a real local model drive the system? Same temporary repo, same real tools and
the same governed loop as scripts/full_pipeline_cases.py, but the decisions come from an actual
model served by Ollama instead of a script. Each goal has an expected token in the answer
(or, for the impossible goal, the expectation that nothing is called).

    python scripts/real_model_tool_probe.py qwen2.5:7b llama3.2:3b --json probe.json

Why a separate script: the pipeline cases test the SYSTEM with a model that cannot be wrong.
This one tests whether a given MODEL is good enough to be used with it. They answer
different questions and must not be mixed up.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

GOALS: List[Dict[str, Any]] = [
    {"name": "read a file", "goal": "Read the file pyproject.toml and tell me the project name", "expect": "sample-service", "tool": "delentia_read_repo_file"},
    {"name": "read another", "goal": "Read the file README.md and tell me its title", "expect": "Sample service", "tool": "delentia_read_repo_file"},
    {"name": "search", "goal": "Search the repository files for the word FDIA and name the file that contains it", "expect": "app.py", "tool": "delentia_search_repo_files"},
    {"name": "remember", "goal": "Remember that the staging database is called orion-stage", "expect": None, "tool": "delentia_remember"},
    {"name": "impossible", "goal": "Book me a flight to Tokyo for next Friday", "expect": None, "tool": None},
]


async def probe(model: str, repeats: int, max_iterations: int, max_seconds: float) -> Dict[str, Any]:
    import full_pipeline_cases as f
    work = Path(tempfile.mkdtemp(prefix="delentia-probe-"))
    env = f.Env(work)
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(env.repo), "DELENTIA_MODEL_CONFIG": str(work / "model.json"),
                       "DELENTIA_LLM_PROVIDER": "ollama", "DELENTIA_LLM_MODEL": model})
    env.build_repo()
    from rct_control_plane.mcp_server import _kernel, mcp
    env.kernel, env.mcp = _kernel, mcp
    rows: List[Dict[str, Any]] = []
    for item in GOALS:
        for attempt in range(repeats):
            loop = env.loop(f"probe-{item['name'].replace(' ', '-')}-{attempt}", max_iterations=max_iterations, max_seconds=max_seconds)
            started = time.perf_counter()
            try:
                result = await loop.run(item["goal"])
                error = None
            except Exception as exc:        # noqa: BLE001 - recorded, not hidden
                result, error = {"steps": [], "stopped_reason": "exception", "final_answer": None}, f"{type(exc).__name__}: {exc}"[:200]
            used = [s.get("tool_name") for s in result.get("steps", []) if s.get("tool_name")]
            answer = str(result.get("final_answer") or "")
            if item["tool"] is None:
                ok = not used and result.get("stopped_reason") in ("llm_finished", "parse_error")
            else:
                ok = item["tool"] in used and (item["expect"] is None or item["expect"].lower() in answer.lower())
            rows.append({"goal": item["name"], "ok": ok, "tools": used, "stopped": result.get("stopped_reason"), "seconds": round(time.perf_counter() - started, 1),
                         "answer": answer[:100], "error": error})
            print(f"  {'OK ' if ok else 'NO '} {item['name']:<12} {rows[-1]['seconds']:>6}s  tools={used}  stopped={rows[-1]['stopped']}", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    return {"model": model, "passed": sum(r["ok"] for r in rows), "total": len(rows), "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--max-iterations", type=int, default=4)
    ap.add_argument("--max-seconds", type=float, default=300.0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    import logging
    logging.disable(logging.WARNING)
    try:
        from loguru import logger
        logger.remove()
    except Exception:
        pass
    results = []
    for model in args.models:
        print(f"model {model}", flush=True)
        results.append(asyncio.run(probe(model, args.repeats, args.max_iterations, args.max_seconds)))
        print(f"  -> {results[-1]['passed']}/{results[-1]['total']}", flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
