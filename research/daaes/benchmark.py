"""
The DAAES benchmark matrix (specification section X, research document 01 sections 8 and 11): the same tasks, the same model, the same wire, the same oracle, several systems, paired seeds.

    arms        b0  a minimal tool-calling agent with no gate (research/plain_agent.py)
                d0  Delentia's governed loop (gate, signatures, taint, policy, journal, audit)
                h0  Hermes Agent v0.22.2 (pinned, its own Python; hermes_adapter.py)
    tasks       TC-003 variants: seed -> a broken `ledgercalc` with k = 2..6 of 18 catalogued defects (tc003_variants.py); the oracle and the hidden tests are the same for every arm
    wire        every arm talks to the model through its OWN `ModelGateway` (model_gateway.py): one place that checks the budget before each call, keeps the real key, counts tokens and cost
    order       the arms of one task run in a seeded random order, so a provider's drift over time is not charged to one arm
    resumable   rows are appended to results.jsonl as they finish; a rerun skips (arm, seed) pairs that are done, so a stopped overnight run continues instead of starting over

What a result means: ONE model on ONE task family. It is evidence about how these systems behave with that model on these tasks, not about the systems in general; a ranking of models needs the same matrix
per model, reported per model and never pooled. A run that crashed in the harness is `valid: false` and listed; a model that timed out or gave up is a valid FAILED run and counts.
Hermes with a real model needs a sandboxed shell (hermes_adapter refuses otherwise); with the scripted stand-in model it does not.
"""
from __future__ import annotations

import json
import os
import random
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from research.daaes import stats
from research.daaes.budget_guard import BudgetPolicy
from research.daaes.model_gateway import ModelGateway

ARMS = ("b0", "d0", "h0")


@contextmanager
def _env(**values: str) -> Iterator[None]:
    """Set variables for one run and put every one of them back (a helper that leaves the environment changed breaks the next run)."""
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _calls_totals(calls_path: Path) -> Dict[str, Any]:
    tokens_in = tokens_out = n = 0
    cost = 0.0
    refused = 0
    if calls_path.exists():
        for line in calls_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("refused"):
                refused += 1
                continue
            n += 1
            tokens_in += int(row.get("prompt_tokens") or 0)
            tokens_out += int(row.get("completion_tokens") or 0)
            cost += float(row.get("cost_usd") or 0.0)
    return {"model_calls": n, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": round(cost, 8), "refused_calls": refused}


def run_cell(arm: str, seed: int, out: Path, upstream_url: str, upstream_key: Optional[str], model: str, price_in: float, price_out: float, policy: BudgetPolicy, *, max_iterations: int,
             max_seconds: float, real_model: bool, hermes_sandboxed: bool, allowed_models: Optional[set] = None) -> Dict[str, Any]:
    """One (arm, task) run behind its own gateway. Never raises: a harness failure becomes a row with valid = false."""
    from research.daaes import tc003
    from rct_control_plane.llm_provider import OpenRouterProvider
    work = out / "runs" / f"{arm}-{seed}"
    wait = str(int(max(90.0, max_seconds)))                                         # every arm waits as long for a slow model (a client-side timeout is not the model failing)
    run_id = f"{arm}-{seed}-{time.time_ns()}"
    started = time.time()
    row: Dict[str, Any] = {"arm": arm, "seed": seed, "valid": False, "passed": False, "score": 0.0, "hard_failures": [], "model": model, "at": started}
    try:
        with ModelGateway(upstream_url, out / "ledger.json", policy, run_id, price_in, price_out, upstream_key=upstream_key, calls_path=work.parent / f"{arm}-{seed}.calls.jsonl", allowed_models=allowed_models,
                          timeout=max(60.0, max_seconds)) as gw:
            if arm == "d0":
                with _env(DELENTIA_OPENROUTER_BASE_URL=gw.base_url, DELENTIA_OPENROUTER_TIMEOUT_S=wait):
                    result = tc003.run_live(OpenRouterProvider(api_key=gw.token, model=model), work, max_iterations=max_iterations, max_seconds=max_seconds, variant_seed=seed)
            elif arm == "b0":
                with _env(DELENTIA_OPENROUTER_BASE_URL=gw.base_url, DELENTIA_LLM_PROVIDER="openrouter", DELENTIA_LLM_MODEL=model, OPENROUTER_API_KEY=gw.token, DELENTIA_EPISODE_BUDGET_USD="0", DELENTIA_OPENROUTER_TIMEOUT_S=wait):
                    result = tc003.run_plain(work, max_iterations=max_iterations, max_seconds=max_seconds, variant_seed=seed)
            elif arm == "h0":
                result = tc003.run_hermes(gw.base_url, gw.token, model, work, max_iterations=max_iterations, max_seconds=max_seconds, variant_seed=seed, real_model=real_model, sandboxed=hermes_sandboxed)
            else:
                raise ValueError(f"unknown arm {arm!r}")
        if result.get("outcome") == "not_evaluated":
            row.update({"outcome": "not_evaluated", "note": result.get("note")})
        else:
            agent = result.get("agent") or {}
            row.update({"valid": True, "passed": bool(result.get("passed")), "score": float(result.get("score") or 0.0), "hard_failures": result.get("hard_failures") or [], "metrics": result.get("metrics"),
                        "k": (result.get("variant") or {}).get("k"), "defects": [d["id"] for d in (result.get("variant") or {}).get("defects", [])], "claim": result.get("claim"),
                        "final_answer": str(agent.get("final_answer") or "")[:700],
                        "stopped_reason": agent.get("stopped_reason") or ("completed" if agent.get("completed") else None), "steps": agent.get("steps") or len(agent.get("tool_calls") or []),
                        "timeout": agent.get("stopped_reason") == "max_seconds_exceeded"})
    except Exception as exc:                                                        # noqa: BLE001 - recorded as an invalid run, listed in the report, never dropped
        row.update({"error": f"{type(exc).__name__}: {str(exc)[:200]}", "trace": traceback.format_exc()[-600:]})
    row.update(_calls_totals(work.parent / f"{arm}-{seed}.calls.jsonl"))
    row["seconds"] = round(time.time() - started, 1)
    return row


def run_matrix(out: Path, upstream_url: str, upstream_key: Optional[str], model: str, price_in: float, price_out: float, arms: List[str], seeds: List[int], *, policy: Optional[BudgetPolicy] = None,
               max_iterations: int = 14, max_seconds: float = 600.0, real_model: bool = True, hermes_sandboxed: bool = False, order_seed: int = 20261017, allowed_models: Optional[set] = None,
               progress: Optional[Any] = None, before_cell: Optional[Any] = None) -> Dict[str, Any]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    done = {(r["arm"], r["seed"]) for r in map(json.loads, results.read_text(encoding="utf-8").splitlines())} if results.exists() else set()
    policy = policy or BudgetPolicy(total_usd=5.0, reserve_usd=0.0, max_cost_per_run_usd=1.0, max_llm_calls_per_run=max_iterations * 6)
    rng = random.Random(order_seed)
    for seed in seeds:
        order = list(arms)
        rng.shuffle(order)
        for arm in order:
            if (arm, seed) in done:
                continue
            if before_cell is not None:
                before_cell(arm, seed)                                              # a rehearsal tells its scripted endpoint which task and arm is about to run
            row = run_cell(arm, seed, out, upstream_url, upstream_key, model, price_in, price_out, policy, max_iterations=max_iterations, max_seconds=max_seconds, real_model=real_model,
                           hermes_sandboxed=hermes_sandboxed, allowed_models=allowed_models)
            with open(results, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            if progress:
                progress(f"seed {seed} {arm:3s} valid={row['valid']} passed={row['passed']} score={row['score']} hard={row['hard_failures']} calls={row.get('model_calls')} {row['seconds']}s")
    rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]
    evaluated = [r for r in rows if r.get("outcome") != "not_evaluated"]
    summary = stats.summarize(evaluated, [a for a in arms if any(r["arm"] == a for r in evaluated)], baseline="b0" if "b0" in arms else None)
    (out / "SUMMARY.md").write_text(_report(summary, rows, model, arms, seeds), encoding="utf-8")
    (out / "SUMMARY.json").write_text(json.dumps({"summary": summary, "model": model, "seeds": seeds}, indent=2, default=str), encoding="utf-8")
    return {"summary": summary, "rows": rows}


def _report(summary: Dict[str, Any], rows: List[Dict[str, Any]], model: str, arms: List[str], seeds: List[int]) -> str:
    not_eval = sorted({r["arm"] for r in rows if r.get("outcome") == "not_evaluated"})
    invalid = [f"{r['arm']}@{r['seed']}: {r.get('error')}" for r in rows if not r["valid"] and r.get("outcome") != "not_evaluated"]
    lines = [f"# DAAES TC-003 matrix, model `{model}`, {len(seeds)} tasks", "",
             "One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.", "",
             stats.render(summary), ""]
    if not_eval:
        lines += ["Not evaluated (a capability the arm does not have, reported, not counted as failure): " + ", ".join(not_eval), ""]
    if invalid:
        lines += ["Invalid runs (harness failures, listed and excluded):"] + [f"- {x}" for x in invalid] + [""]
    by_k: Dict[Any, Dict[str, List[bool]]] = {}
    for r in rows:
        if r["valid"] and r.get("k"):
            by_k.setdefault(r["k"], {}).setdefault(r["arm"], []).append(bool(r["passed"]))
    if by_k:
        lines += ["Pass rate by number of defects (k):", "", "| k | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
        for k in sorted(by_k):
            lines.append(f"| {k} | " + " | ".join((f"{sum(by_k[k].get(a, []))}/{len(by_k[k].get(a, []))}" if by_k[k].get(a) else "-") for a in arms) + " |")
    return "\n".join(lines) + "\n"
