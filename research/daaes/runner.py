"""
The DAAES runner: runs a case on an arm, writes the sealed evidence bundle, and can run the whole zero-cost suite.

    python -m research.daaes run  --case TC-009 --arm delentia_delta_engine --seed 1701 --out results
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

from research.daaes import bundle, tc003, tc006, tc009, tc010, tc025

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


def _bundle(out: Path, date: str, case: str, arm: str, seed: int, result: Dict[str, Any], keyfile: Path) -> Dict[str, Any]:
    folder = out / date / case / arm / str(seed)
    _clean(folder)
    score = {k: result.get(k) for k in ("score", "passed", "hard_failures", "metrics", "weights", "threshold")}
    oracle = {k: v for k, v in result.items() if k not in ("events_path", "receipts", "child_stderr")}
    bundle.write_bundle(folder, case_id=case, arm=arm, seed=seed, fixture_sha256=result.get("fixture_sha256") or "n/a", events_path=Path(result["events_path"]) if result.get("events_path") else None,
                        agent_result={"arm": arm, "summary": {k: result.get(k) for k in ("completed", "claim", "executed_calls", "gate_outcomes", "launches", "durable") if k in result}},
                        oracle_result=oracle, score=score, replay_report=(result.get("sections") or {"mode": "not_evaluated"}), receipts=result.get("receipts"))
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
    variant = "_".join(str(kw[k]) for k in ("kill_point", "policy", "fault") if kw.get(k) not in (None, "none"))
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
    elif case == "TC-003":
        policy, fault = kw.get("policy", "perfect"), kw.get("fault", "F0")
        result = tc003.run_tc003(arm, policy, fault, work)
        arm = f"{arm}@{policy}@{fault}"
    else:
        raise ValueError(f"unknown case {case}")
    sealed = _bundle(out, date, case, arm, seed, result, keyfile)
    return {"case": case, "arm": arm, "seed": seed, "passed": result.get("passed"), "score": result.get("score"), "hard_failures": result.get("hard_failures"), **sealed}


def suite_plan(quick: bool = True) -> List[Tuple[str, str, Dict[str, Any]]]:
    plan: List[Tuple[str, str, Dict[str, Any]]] = []
    for arm in ("ref_snapshot", "ref_delta", "delentia_delta_engine", "delentia_memory_log"):
        plan.append(("TC-009", arm, {}))
    for arm in ("event_log_baseline", "delentia"):
        plan.append(("TC-025", arm, {}))
    for arm in ("reference", "naive_new_key", "delentia"):
        for point in (tc010.POINTS if not quick else ("none", "pre_call", "in_flight", "after_commit_pre_receipt")):
            plan.append(("TC-010", arm, {"kill_point": point}))
    for arm in tc006.ARMS:
        plan.append(("TC-006", arm, {}))
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
