"""
R4 "Live Rerun" of TC-025 (specification: Replay Modes; research document 6.2 item 10): run the SAME task through the governed loop with a real model several times and report how much the behaviour VARIES.

The specification says R4 must not be required to match 100%: a model, its hardware, a provider and sampling make answers differ even at a low temperature. So this module never asks for identity. It measures:
  sequence stability      the share of runs whose ordered list of tool calls is the same as the most common one, and how many distinct sequences there were
  answer stability        the share of runs whose normalised final answer is the same as the most common one
  correctness             the share of runs whose answer the ORACLE accepts (it reads the fixture's own numbers, never the agent's account)
  stopped reasons, time   how the runs ended and how long they took
A rate over n runs comes with its exact 95% (Clopper-Pearson) interval, so six runs are not mistaken for a measurement of a model.

`run(n, provider_factory, ...)` takes a callable that makes a fresh provider per run: a real one (`OllamaProvider`) for the measurement, a scripted nondeterministic one for the tests of this code.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from research.daaes import delentia_session as ds
from research.daaes import stats

FILES = {"project/pyproject.toml": "[project]\nname = \"ledgercalc\"\nversion = \"0.3.1\"\n", "project/README.md": "ledgercalc computes totals.\n"}
GOAL = "Read project/pyproject.toml and tell me the project name and the version."
EXPECTED = ("ledgercalc", "0.3.1")
POLICY = {"version": "1.0.0", "policy_id": "r4-owner", "default_fallback_A": 0, "custom_safety_threshold": 0.5,
          "rules": [{"rule_id": "R-READ", "intent_patterns": ["read_repo_file", "search_repo_files", "recall"], "action_type": "ALLOW", "assigned_A": 1}],
          "blocked_action_patterns": [], "require_human_dual_signoff": [], "roles": {"default_role": "developer", "principals": {}}, "jury_by_risk": {}}


class R4World(ds.DirWorld):
    """The workspace with the REAL definition of the read tool (name, description, argument names). The scripted worlds never needed to describe their tools; a live model that is not told the argument is
    `relative_path` guesses another name and gets an error (found by the first R4 run, whose six "cannot read the file" answers measured this harness, not the model)."""

    async def list_tools(self) -> List[Any]:
        from rct_control_plane.mcp_server import mcp
        real = {t.name: t for t in await mcp.list_tools()}
        return [real[name] for name in ("delentia_read_repo_file", "delentia_search_repo_files") if name in real]


def normalise(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9. ]+", "", re.sub(r"\s+", " ", (text or "").lower())).strip()


def correct(answer: Optional[str]) -> bool:
    low = (answer or "").lower()
    return all(token in low for token in EXPECTED)


def one_run(index: int, provider: Any, work: Path, max_seconds: float) -> Dict[str, Any]:
    run_dir = work / f"run-{index}-{time.time_ns()}"
    run_dir.mkdir(parents=True)
    world = R4World(run_dir / "workspace")
    for rel, text in FILES.items():
        target = run_dir / "workspace" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    policy = run_dir / "owner_policy.json"
    policy.write_text(json.dumps(POLICY), encoding="utf-8")
    started = time.time()
    summary = ds.run_session(run_dir / "home", GOAL, [], world, None, namespace=f"r4-{index}", policy_path=policy, max_iterations=6, route=False, provider=provider, max_seconds=max_seconds)
    sequence = [str(s["tool"]) for s in (summary.get("steps") or []) if s.get("tool")]                  # tool calls only: the closing "finish" step is not a call
    return {"index": index, "sequence": sequence, "answer": summary.get("final_answer"), "stopped": summary.get("stopped_reason"), "correct": correct(summary.get("final_answer")), "seconds": round(time.time() - started, 1)}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    seqs = Counter(tuple(r["sequence"]) for r in rows)
    answers = Counter(normalise(r["answer"]) for r in rows)
    top_seq = seqs.most_common(1)[0][1] if rows else 0
    top_ans = answers.most_common(1)[0][1] if rows else 0
    ok = sum(1 for r in rows if r["correct"])

    def rate(k: int) -> Dict[str, Any]:
        low, high = stats.proportion_ci(k, n) if n else (0.0, 1.0)
        return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": [round(low, 4), round(high, 4)]}
    return {"runs": n, "sequence_stability": rate(top_seq), "distinct_sequences": len(seqs), "answer_stability": rate(top_ans), "distinct_answers": len(answers), "correct": rate(ok),
            "stopped_reasons": dict(Counter(str(r["stopped"]) for r in rows)), "seconds": {"min": min((r["seconds"] for r in rows), default=None), "max": max((r["seconds"] for r in rows), default=None)}}


def run(n: int, provider_factory: Callable[[int], Any], work: Path, max_seconds: float = 900.0, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for i in range(1, n + 1):
        row = one_run(i, provider_factory(i), work, max_seconds)
        rows.append(row)
        if progress:
            progress(f"run {i}: {row['stopped']} correct={row['correct']} seq={row['sequence']} {row['seconds']}s")
    return {"summary": summarize(rows), "rows": rows}


def render(result: Dict[str, Any], model: str) -> str:
    s = result["summary"]
    lines = [f"# TC-025 R4 live rerun, model `{model}`, {s['runs']} runs of the same task", "",
             "Not required to be identical: this measures how much a live model varies. One task, one model; not a ranking of models.", "",
             f"- same tool sequence as the most common one: {s['sequence_stability']['k']}/{s['runs']} (95% exact {s['sequence_stability']['ci95'][0]}-{s['sequence_stability']['ci95'][1]}); distinct sequences: {s['distinct_sequences']}",
             f"- same normalised final answer as the most common one: {s['answer_stability']['k']}/{s['runs']} (95% exact {s['answer_stability']['ci95'][0]}-{s['answer_stability']['ci95'][1]}); distinct answers: {s['distinct_answers']}",
             f"- answer accepted by the oracle: {s['correct']['k']}/{s['runs']} (95% exact {s['correct']['ci95'][0]}-{s['correct']['ci95'][1]})",
             f"- stopped reasons: {s['stopped_reasons']}; run time {s['seconds']['min']}-{s['seconds']['max']} s", "", "| run | stopped | correct | tool sequence | seconds |", "|---|---|---|---|---|"]
    for r in result["rows"]:
        lines.append(f"| {r['index']} | {r['stopped']} | {r['correct']} | {' > '.join(r['sequence']) or '-'} | {r['seconds']} |")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import os
    parser = argparse.ArgumentParser(description="TC-025 R4: the same task through the governed loop n times with a real local model; reports the variation, never demands identity")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--runs", type=int, default=6)
    parser.add_argument("--max-seconds", type=float, default=900.0)
    parser.add_argument("--out", default=str(Path.home() / "daaes-results" / "r4"))
    args = parser.parse_args(argv)
    from rct_control_plane.llm_provider import OllamaProvider
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DELENTIA_OLLAMA_TIMEOUT_S", "600")
    result = run(args.runs, lambda i: OllamaProvider(model=args.model), out, args.max_seconds, progress=print)
    (out / "R4.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    text = render(result, args.model)
    (out / "R4.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
