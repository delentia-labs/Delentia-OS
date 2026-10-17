"""
The DAAES runner: runs a case on an arm, writes the sealed evidence bundle, and can run the whole zero-cost suite.

    python -m research.daaes run  --case TC-009 --arm delentia_delta_log --seed 1701 --out results
    python -m research.daaes suite --out results [--quick]          # every zero-cost case and arm; prints the table; writes SUITE.md
    python -m research.daaes verify results/<date>/<case>/<arm>/<seed>
    python -m research.daaes checklist --out results                # the seven items that must hold before any paid model call

No model is called, no key is read, nothing leaves the machine. Arms that need something not built yet (Hermes, a live model) are listed as `not_evaluated`, never as failures.
"""
from __future__ import annotations

import gc
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from research.daaes import bundle, run_manifest, tc003, tc005, tc006, tc007_tc020, tc009, tc010, tc013, tc025, tc027, tc028
from research.daaes import events as ev

NOT_EVALUATED = {"hermes": "no Hermes adapter yet: the pinned repository has not been cloned, so no claim is made for or against it",
                 "live_model": "needs a capable model and a key (the live pilot, C3/C4 of the roadmap)"}


def _clean(path: Path) -> None:
    """Remove a work folder. On Windows a SQLite file stays locked until its connection is collected, so collect and retry; a folder that still cannot go is moved aside, never reused."""
    for attempt in range(4):
        if not path.exists():
            return
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.2 * (attempt + 1))
    if path.exists():
        path.rename(path.with_name(path.name + f".stale-{time.time_ns()}"))


def _bundle(out: Path, date: str, case: str, arm: str, seed: int, result: Dict[str, Any], keyfile: Path, kw: Optional[Dict[str, Any]] = None, live: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    folder = out / date / case / arm / str(seed)
    _clean(folder)
    score = {k: result.get(k) for k in ("score", "passed", "hard_failures", "metrics", "weights", "threshold")}
    oracle = {k: v for k, v in result.items() if k not in ("events_path", "receipts", "child_stderr")}
    bundle.write_bundle(folder, case_id=case, arm=arm, seed=seed, fixture_sha256=result.get("fixture_sha256") or "n/a", events_path=Path(result["events_path"]) if result.get("events_path") else None,
                        agent_result={"arm": arm, "summary": {k: result.get(k) for k in ("completed", "claim", "executed_calls", "gate_outcomes", "launches", "durable") if k in result}},
                        oracle_result=oracle, score=score, replay_report=(result.get("sections") or {"mode": "not_evaluated"}), receipts=result.get("receipts"),
                        run_manifest_data=run_manifest.for_run(case, arm, seed, result, ev.load(Path(result["events_path"])) if result.get("events_path") and Path(result["events_path"]).exists() else [], kw, live))
    seal = bundle.seal(folder, keyfile)
    return {"folder": str(folder), "bundle_sha256": seal["bundle_sha256"], "verified": bundle.verify_bundle(folder, seal.get("public_key"))["valid"]}


def run_one(case: str, arm: str, seed: int, out: Path, date: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
    """A case run may set environment variables for the code under test (key folders, switches). Whatever it set is undone afterwards: a run must not change the next one."""
    saved = dict(os.environ)
    try:
        return _run_one(case, arm, seed, out, date, **kw)
    finally:
        os.environ.clear()
        os.environ.update(saved)
        gc.collect()


def _run_one(case: str, arm: str, seed: int, out: Path, date: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
    out = Path(out)
    date = date or time.strftime("%Y-%m-%d")
    variant = "_".join(str(kw[k]) for k in ("kill_point", "policy", "fault", "behaviour") if kw.get(k) not in (None, "none"))
    work = out / ".work" / case / (f"{arm}__{variant}" if variant else arm) / str(seed)
    _clean(work)
    work.mkdir(parents=True)
    keyfile = out / ".keys" / "bundle-seal.pem"                      # outside every bundle: the folder a reader copies does not hold the key
    if case == "TC-009":
        from research.daaes import events as ev
        log = ev.RunLog(work / "events.jsonl", f"tc009-{arm}-{seed}")
        baseline = kw.get("baseline_total_bytes")
        profile = kw.get("profile") or ("memory" if arm == "delentia_memory_log" else "small")
        result = tc009.run_tc009(arm, work / "store", seed=seed, profile=profile, fault_ops=kw.get("fault_ops", 60), baseline_total_bytes=baseline, log=log)
        result["events_path"] = str(work / "events.jsonl")
    elif case == "TC-025":
        result = tc025.run_tc025(arm, work, seed)
    elif case == "TC-010":
        result = tc010.run_case(arm, kw.get("kill_point", "none"), work, seed)
        arm = f"{arm}@{kw.get('kill_point', 'none')}"
    elif case == "TC-006":
        result = tc006.run_tc006(arm, work)
    elif case == "TC-028":
        behaviour = kw.get("behaviour", "runbook")
        result = tc028.run_tc028(arm, work, behaviour, seed)
        arm = f"{arm}@{behaviour}"
    elif case == "TC-027":
        behaviour = kw.get("behaviour", "careful")
        result = tc027.run_tc027(arm, work, behaviour, seed)
        arm = f"{arm}@{behaviour}"
    elif case == "TC-005":
        result = tc005.run_tc005(arm, work, seed)
    elif case == "TC-013":
        behaviour = kw.get("behaviour", "perfect")
        result = tc013.run_tc013(arm, work, behaviour, seed)
        arm = f"{arm}@{behaviour}"
    elif case == "TC-007":
        result = tc007_tc020.run_tc007(arm, work)
    elif case == "TC-020":
        result = tc007_tc020.run_tc020(arm, work)
    elif case == "TC-003":
        policy, fault = kw.get("policy", "perfect"), kw.get("fault", "F0")
        result = tc003.run_tc003(arm, policy, fault, work)
        arm = f"{arm}@{policy}@{fault}"
    else:
        raise ValueError(f"unknown case {case}")
    sealed = _bundle(out, date, case, arm, seed, result, keyfile, kw)
    return {"case": case, "arm": arm, "seed": seed, "passed": result.get("passed"), "score": result.get("score"), "hard_failures": result.get("hard_failures"), **sealed}


def run_live(case: str, kind: str, model: str, out: Path, *, seed: int = 1701, fault: str = "F0", budget_usd: float = 0.0, price_in: Optional[float] = None, price_out: Optional[float] = None,
             max_iterations: int = 14, max_seconds: Optional[float] = None, variant_seed: Optional[int] = None, date: Optional[str] = None) -> Dict[str, Any]:
    """One live run: Delentia's governed loop with a REAL model, the experiment budget guard in front of it, the same oracle, a sealed bundle.

    kind 'ollama'     a local model: free, so the price is 0 and nothing can be spent.
    kind 'openrouter' a paid model: refused unless OPENROUTER_API_KEY is set AND DELENTIA_RUN_LIVE_TESTS=1 AND both prices AND a budget are given. The key is read from the environment and never written anywhere.
    Not part of `suite`: a live run costs time (local) or money (paid) and its result is about one model."""
    import os

    from research.daaes import budget_guard, live_adapter
    from rct_control_plane.llm_provider import OllamaProvider
    if case != "TC-003":
        raise ValueError("only TC-003 has a live adapter so far")
    out = Path(out)
    date = date or time.strftime("%Y-%m-%d")
    arm = f"d0_live-{kind}-{model.replace('/', '_').replace(':', '_')}" + (f"-v{variant_seed}" if variant_seed is not None else "")
    if kind == "ollama":
        inner: Any = OllamaProvider(model=model)
        pin, pout = 0.0, 0.0
        policy = budget_guard.BudgetPolicy(total_usd=5.0, reserve_usd=0.0, max_cost_per_run_usd=1.0, max_llm_calls_per_run=max_iterations * 3, max_input_tokens_per_run=2_000_000, max_output_tokens_per_run=500_000)
    elif kind == "openrouter":
        if not os.environ.get("OPENROUTER_API_KEY") or os.environ.get("DELENTIA_RUN_LIVE_TESTS") != "1":
            raise budget_guard.BudgetExceeded("a paid run needs OPENROUTER_API_KEY and DELENTIA_RUN_LIVE_TESTS=1 in the environment (set by you, never written by this tool)")
        if price_in is None or price_out is None or budget_usd <= 0:
            raise budget_guard.BudgetExceeded("a paid run needs --price-in, --price-out (USD per million tokens) and --budget-usd: an unknown price is refused")
        inner = live_adapter.openrouter_provider(model)
        pin, pout = price_in, price_out
        policy = budget_guard.BudgetPolicy(total_usd=budget_usd, warning_usd=budget_usd * 0.6, stop_new_runs_usd=budget_usd * 0.8, reserve_usd=budget_usd * 0.2,
                                           max_cost_per_run_usd=budget_usd * 0.5, max_llm_calls_per_run=max_iterations * 3)
    else:
        raise ValueError("kind is 'ollama' or 'openrouter'")
    work = out / ".work" / case / arm / str(seed)
    _clean(work)
    work.mkdir(parents=True)
    guard = live_adapter.guarded(inner, out / "live_ledger.json", policy, f"{arm}-{seed}-{time.time_ns()}", pin, pout)
    started = time.time()
    result = tc003.run_live(guard, work, fault=fault, max_iterations=max_iterations, max_seconds=max_seconds if max_seconds is not None else (3600.0 if kind == "ollama" else 300.0), variant_seed=variant_seed)
    result["guard_refused"] = guard.refused
    result["seconds"] = round(time.time() - started, 1)
    live_facts = {"model": model, "provider": kind, "api_mode": ("Ollama native API" if kind == "ollama" else "OpenRouter chat completions"),
                  "budget": {"usd": policy.total_usd, "max_llm_calls_per_run": policy.max_llm_calls_per_run, "seconds": max_seconds if max_seconds is not None else (3600.0 if kind == "ollama" else 300.0),
                             "price_in_per_million": pin, "price_out_per_million": pout},
                  "network_policy": ("only the local Ollama server on loopback" if kind == "ollama" else "only the provider's endpoint, behind the budget guard; the key is read from the environment, never written")}
    sealed = _bundle(out, date, case, arm, seed, result, out / ".keys" / "bundle-seal.pem", {"fault": fault}, live_facts)
    return {"case": case, "arm": arm, "seed": seed, "passed": result.get("passed"), "score": result.get("score"), "hard_failures": result.get("hard_failures"),
            "seconds": result["seconds"], "agent": result.get("agent"), "guard_refused": guard.refused, **sealed}


def _browser_available() -> bool:
    """TC-027 needs a real headless browser; a machine without one has a suite without that case (it is never counted as a failure)."""
    from rct_control_plane import browser_tool
    return bool(browser_tool.find_browser())


def suite_plan(quick: bool = True) -> List[Tuple[str, str, Dict[str, Any]]]:
    plan: List[Tuple[str, str, Dict[str, Any]]] = []
    for arm in ("ref_snapshot", "ref_delta", "delentia_delta_engine_r82", "delentia_delta_log", "delentia_memory_log"):
        plan.append(("TC-009", arm, {}))
    for arm in ("event_log_baseline", "delentia"):
        plan.append(("TC-025", arm, {}))
    for arm in ("reference", "naive_new_key", "delentia"):
        for point in (tc010.POINTS if not quick else ("none", "pre_call", "in_flight", "after_commit_pre_receipt")):
            plan.append(("TC-010", arm, {"kill_point": point}))
    for arm in tc006.ARMS:
        plan.append(("TC-006", arm, {}))
    for arm in tc005.ARMS:
        plan.append(("TC-005", arm, {}))
    for arm, behaviour in (("delentia", "runbook"), ("delentia", "reckless"), ("delentia", "blind"), ("delentia_careless", "reckless"), ("floor_only_careless", "reckless")):
        plan.append(("TC-028", arm, {"behaviour": behaviour}))
    if _browser_available():
        for arm, behaviour in (("delentia", "careful"), ("delentia", "stale"), ("delentia", "hijacked"), ("delentia_careless", "hijacked"), ("floor_only_careless", "hijacked")):
            plan.append(("TC-027", arm, {"behaviour": behaviour}))
    for arm, behaviours in (("delentia", tc013.BEHAVIOURS), ("delentia_careless", ("buys",)), ("floor_only_careless", ("perfect", "buys"))):
        for behaviour in behaviours:
            plan.append(("TC-013", arm, {"behaviour": behaviour}))
    for arm in tc007_tc020.TC007_ARMS:
        plan.append(("TC-007", arm, {}))
    for arm in tc007_tc020.TC020_ARMS:
        plan.append(("TC-020", arm, {}))
    for arm in tc003.ARMS:
        for policy in (tc003.POLICIES if not quick else ("perfect", "tampering", "unauthorized_write", "forged_claim")):
            plan.append(("TC-003", arm, {"policy": policy, "fault": "F0"}))
    return plan


def run_suite(out: Path, seed: int = 1701, quick: bool = True, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    out = Path(out)
    date = time.strftime("%Y-%m-%d")
    rows: List[Dict[str, Any]] = []
    baselines: Dict[str, int] = {}
    for case, arm, kw in suite_plan(quick):
        if case == "TC-009":
            profile = "memory" if arm == "delentia_memory_log" else "small"
            if arm != "ref_snapshot":
                kw = {**kw, "baseline_total_bytes": baselines.get(profile) or baselines.setdefault(profile, _baseline_bytes(out, seed, profile))}
            else:
                kw = {**kw, "profile": "small"}
        row = run_one(case, arm, seed, out, date, **kw)
        rows.append(row)
        if progress:
            progress(f"{case:7s} {row['arm']:48s} passed={row['passed']!s:5s} score={row['score']!s:7s} sealed={row['verified']}")
    summary = {"date": date, "seed": seed, "quick": quick, "runs": rows, "not_evaluated": NOT_EVALUATED, "all_bundles_valid": all(r["verified"] for r in rows)}
    bundle.write_json(out / date / "SUITE.json", summary)
    (out / date / "SUITE.md").write_text(render_suite(summary), encoding="utf-8")
    return summary


def _baseline_bytes(out: Path, seed: int, profile: str) -> int:
    work = out / ".work" / "baseline" / profile
    _clean(work)
    return int(tc009.run_tc009("ref_snapshot", work, seed=seed, profile=profile, fault_ops=60)["storage"]["total_bytes"])


def render_suite(summary: Dict[str, Any]) -> str:
    lines = [f"# DAAES zero-cost suite, {summary['date']} (seed {summary['seed']}{', quick' if summary['quick'] else ''})", "",
             "No model, no key, no network. Every row is a sealed evidence bundle; `python -m research.daaes verify <folder>` re-checks it.", "",
             "| case | arm | passed | score | hard failures | bundle sealed and valid |", "|---|---|---|---|---|---|"]
    for r in summary["runs"]:
        lines.append(f"| {r['case']} | {r['arm']} | {r['passed']} | {r['score']} | {', '.join(map(str, r['hard_failures'] or [])) or '-'} | {r['verified']} |")
    lines += ["", "## Not evaluated", ""] + [f"- **{k}**: {v}" for k, v in summary["not_evaluated"].items()]
    lines += ["", f"All bundles valid: **{summary['all_bundles_valid']}**.", ""]
    return "\n".join(lines)


def load_suite(out: Path) -> Optional[Dict[str, Any]]:
    files = sorted(Path(out).glob("*/SUITE.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None
