"""
Round 54: do batches and the Tool Forge work with a REAL model, and what do they cost in tokens?

Same temporary repository, real tools and governed loop as scripts/real_model_tool_probe.py; the decisions and the code come
from a model served by Ollama (free, local) or any model you point the agent at. Two parts:

  forge   the model writes ten small pure functions from a one-line spec; each is checked statically and run against a smoke
          test WRITTEN BY A HUMAN (here: by this script). Reports how many pass, where the rest fail, seconds, tokens.
  batch   four goals that need several independent reads, run twice: with batching off (one tool per decision) and on
          (`call_tools`). Reports correctness, model calls, seconds and prompt/completion tokens per episode.

The token numbers are the measured input for the budget in the Round 54 report: they are what a paid model would be billed for.

    python scripts/real_model_round54_probe.py qwen2.5:7b --part both --json out.json
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

FORGE_SPECS: List[Dict[str, str]] = [
    {"name": "slugify", "spec": "turn a title into a lowercase url slug using hyphens, dropping punctuation",
     "test": 'assert slugify("Hello World") == "hello-world"\nassert slugify("  A  B! ") == "a-b"\nassert slugify("") == ""'},
    {"name": "vowel_count", "spec": "count the vowels (a, e, i, o, u, either case) in a text",
     "test": 'assert vowel_count("Hello") == 2\nassert vowel_count("xyz") == 0\nassert vowel_count("AEIOU") == 5'},
    {"name": "c_to_f", "spec": "convert a temperature in celsius to fahrenheit, rounded to one decimal place",
     "test": 'assert c_to_f(0) == 32.0\nassert c_to_f(100) == 212.0\nassert c_to_f(-40) == -40.0'},
    {"name": "is_palindrome", "spec": "return True when a text reads the same backwards ignoring case, spaces and punctuation",
     "test": 'assert is_palindrome("A man, a plan, a canal: Panama") is True\nassert is_palindrome("hello") is False\nassert is_palindrome("") is True'},
    {"name": "median", "spec": "return the median of a non-empty list of numbers (the mean of the two middle values for an even count)",
     "test": 'assert median([3, 1, 2]) == 2\nassert median([4, 1, 3, 2]) == 2.5\nassert median([7]) == 7'},
    {"name": "to_roman", "spec": "convert an integer from 1 to 3999 to a roman numeral string",
     "test": 'assert to_roman(4) == "IV"\nassert to_roman(1994) == "MCMXCIV"\nassert to_roman(3999) == "MMMCMXCIX"'},
    {"name": "camel_to_snake", "spec": "convert a camelCase or PascalCase identifier to snake_case",
     "test": 'assert camel_to_snake("camelCase") == "camel_case"\nassert camel_to_snake("HTTPServer") == "http_server"\nassert camel_to_snake("simple") == "simple"'},
    {"name": "add_days", "spec": "given an ISO date string YYYY-MM-DD and a number of days, return the ISO date string that many days later",
     "test": 'assert add_days("2026-01-30", 3) == "2026-02-02"\nassert add_days("2024-02-28", 2) == "2024-03-01"\nassert add_days("2026-10-02", 0) == "2026-10-02"'},
    {"name": "top_word", "spec": "return the most frequent word in a text, lowercased, ties broken alphabetically",
     "test": 'assert top_word("the cat and the hat") == "the"\nassert top_word("b a b a") == "a"\nassert top_word("One") == "one"'},
    {"name": "clamp", "spec": "limit a number to the inclusive range low..high",
     "test": 'assert clamp(5, 0, 3) == 3\nassert clamp(-1, 0, 3) == 0\nassert clamp(2, 0, 3) == 2'},
]

BATCH_GOALS: List[Dict[str, Any]] = [
    {"name": "three files", "goal": "Read pyproject.toml, README.md and src/app.py, then tell me the project name and the title of the README", "expect": ["sample-service", "Sample service"]},
    {"name": "notes + version", "goal": "Look at docs/notes.md and pyproject.toml and tell me who the release manager is and the project version", "expect": ["Somchai", "0.3.1"]},
    {"name": "search + read", "goal": "Search the repository for the word FDIA and also read README.md; name the file that contains FDIA and the README title", "expect": ["app.py", "Sample service"]},
    {"name": "four files", "goal": "Read README.md, pyproject.toml, docs/notes.md and src/app.py and report the name of the staging database", "expect": ["orion-stage"]},
]


async def forge_part(model: str) -> Dict[str, Any]:
    from rct_control_plane.llm_provider import MeteredProvider, OllamaProvider
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.tool_forge import ToolForge
    work = Path(tempfile.mkdtemp(prefix="delentia-forge-probe-"))
    os.environ["DELENTIA_HOME"] = str(work / "home")
    forge = ToolForge(ControlPlanePersistence(db_path=str(work / "forge.db")))
    rows: List[Dict[str, Any]] = []
    for item in FORGE_SPECS:
        provider = MeteredProvider(OllamaProvider(model=model), prompt_price_per_mtok=0.0, completion_price_per_mtok=0.0)
        started = time.perf_counter()
        try:
            proposal = await forge.propose(item["name"], item["spec"], item["test"], provider=provider)
            status, stage = proposal.status, proposal.verification.get("stage")
            problems = proposal.verification.get("problems", [])[:1]
        except Exception as exc:                          # noqa: BLE001 - recorded
            status, stage, problems = "ERROR", "exception", [f"{type(exc).__name__}: {exc}"[:120]]
        cost = {"prompt_tokens": provider.prompt_tokens, "completion_tokens": provider.completion_tokens}
        rows.append({"tool": item["name"], "status": status, "stage": stage, "problems": problems, "seconds": round(time.perf_counter() - started, 1),
                     "prompt_tokens": cost.get("prompt_tokens"), "completion_tokens": cost.get("completion_tokens")})
        print(f"  {'OK ' if status == 'VERIFIED' else 'NO '} {item['name']:<15} {rows[-1]['seconds']:>6}s  {status}  {problems}", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    return {"verified": sum(r["status"] == "VERIFIED" for r in rows), "total": len(rows), "rows": rows}


async def batch_part(model: str, max_seconds: float) -> Dict[str, Any]:
    import full_pipeline_cases as f
    work = Path(tempfile.mkdtemp(prefix="delentia-batch-probe-"))
    env = f.Env(work)
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(env.repo), "DELENTIA_MODEL_CONFIG": str(work / "model.json"),
                       "DELENTIA_LLM_PROVIDER": "ollama", "DELENTIA_LLM_MODEL": model})
    env.build_repo()
    from rct_control_plane.mcp_server import _kernel, mcp
    env.kernel, env.mcp = _kernel, mcp
    arms: Dict[str, List[Dict[str, Any]]] = {}
    for arm, flag in (("one tool per decision", None), ("batching on", "1")):
        if flag is None:
            os.environ.pop("DELENTIA_PARALLEL_TOOLS", None)
        else:
            os.environ["DELENTIA_PARALLEL_TOOLS"] = flag
        arms[arm] = []
        for index, item in enumerate(BATCH_GOALS):
            loop = env.loop(f"b54-{'on' if flag else 'off'}-{index}", max_iterations=6, max_seconds=max_seconds)
            started = time.perf_counter()
            try:
                result = await loop.run(item["goal"])
                error = None
            except Exception as exc:                      # noqa: BLE001 - recorded
                result, error = {"steps": [], "stopped_reason": "exception", "final_answer": None, "cost": {}}, f"{type(exc).__name__}: {exc}"[:150]
            answer = str(result.get("final_answer") or "")
            steps = result.get("steps", [])
            cost = result.get("cost") or {}
            batch_steps = sum(1 for s in steps if "[batch" in str(s.get("llm_reasoning", "")))
            correct = all(token.lower() in answer.lower() for token in item["expect"])
            arms[arm].append({"goal": item["name"], "correct": correct, "model_calls": cost.get("calls"), "tool_steps": sum(1 for s in steps if s.get("tool_name")),
                              "batched_tool_steps": batch_steps, "seconds": round(time.perf_counter() - started, 1), "prompt_tokens": cost.get("prompt_tokens"),
                              "completion_tokens": cost.get("completion_tokens"), "stopped": result.get("stopped_reason"), "error": error, "answer": answer[:90]})
            r = arms[arm][-1]
            print(f"  {'OK ' if correct else 'NO '} [{arm}] {item['name']:<16} calls={r['model_calls']} tools={r['tool_steps']} batched={batch_steps} {r['seconds']}s tokens={r['prompt_tokens']}+{r['completion_tokens']}", flush=True)
    os.environ.pop("DELENTIA_PARALLEL_TOOLS", None)
    shutil.rmtree(work, ignore_errors=True)

    def summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = max(1, len(rows))
        return {"correct": sum(r["correct"] for r in rows), "of": len(rows), "mean_model_calls": round(sum(r["model_calls"] or 0 for r in rows) / n, 2),
                "mean_seconds": round(sum(r["seconds"] for r in rows) / n, 1), "mean_prompt_tokens": round(sum(r["prompt_tokens"] or 0 for r in rows) / n),
                "mean_completion_tokens": round(sum(r["completion_tokens"] or 0 for r in rows) / n), "episodes_that_used_a_batch": sum(1 for r in rows if r["batched_tool_steps"])}
    return {"arms": {name: {"summary": summary(rows), "rows": rows} for name, rows in arms.items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--part", choices=["forge", "batch", "both"], default="both")
    parser.add_argument("--max-seconds", type=float, default=400.0)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    import logging
    logging.disable(logging.WARNING)
    try:
        from loguru import logger as _loguru
        _loguru.remove()
    except Exception:
        pass
    out: Dict[str, Any] = {}
    for model in args.models:
        out[model] = {}
        if args.part in ("forge", "both"):
            print(f"\n== {model}: Tool Forge ==", flush=True)
            out[model]["forge"] = asyncio.run(forge_part(model))
        if args.part in ("batch", "both"):
            print(f"\n== {model}: batching ==", flush=True)
            out[model]["batch"] = asyncio.run(batch_part(model, args.max_seconds))
    text = json.dumps(out, indent=2, ensure_ascii=False)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    for model, parts in out.items():
        if "forge" in parts:
            print(f"{model} forge: {parts['forge']['verified']}/{parts['forge']['total']} verified")
        for arm, data in parts.get("batch", {}).get("arms", {}).items():
            print(f"{model} {arm}: {data['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
