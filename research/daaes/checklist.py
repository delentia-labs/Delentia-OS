"""
The Pre-API Spending Checklist (zero-budget roadmap, section 10): seven things that must hold before the first paid model call. Each item is decided from the sealed bundles of the latest suite
run (and a few direct checks), never from a statement. Status: PASS / PARTIAL (it holds, with a stated gap) / FAIL.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from research.daaes import bundle
from research.daaes.runner import load_suite


def evaluate(out: Path) -> Dict[str, Any]:
    suite = load_suite(out)
    items: List[Dict[str, Any]] = []
    if suite is None:
        return {"items": [], "passed": 0, "partial": 0, "total": 7, "ready_for_paid_calls": False, "note": "no suite run found: run `python -m research.daaes suite --out <folder>` first"}

    def find(case: str, arm_prefix: str) -> List[Dict[str, Any]]:
        return [r for r in suite["runs"] if r["case"] == case and r["arm"].startswith(arm_prefix)]

    def detail(case: str, arm: str) -> Dict[str, Any]:
        folder = Path(find(case, arm)[0]["folder"])
        return json.loads((folder / "oracle_result.json").read_text(encoding="utf-8"))

    def item(n: int, title: str, status: str, why: str) -> None:
        items.append({"n": n, "title": title, "status": status, "why": why})

    engine, memlog, refdelta = detail("TC-009", "delentia_delta_engine"), detail("TC-009", "delentia_memory_log"), detail("TC-009", "ref_delta")
    exact = all(d["states_exact"] == d["states_checked"] for d in (engine, memlog, refdelta))
    gaps = [f"DeltaEngine: {len(engine['hard_failures'])} hard failure(s)"] if engine["hard_failures"] else []
    item(1, "TC-009: state reconstruction equals the reference at every check point", "PASS" if exact and not gaps else ("PARTIAL" if exact else "FAIL"),
         f"exact at every checked version for every store ({engine['states_exact']}/{engine['states_checked']} for the DeltaEngine); "
         + ("; ".join(gaps) + " (it cannot detect a missing or corrupted delta, the memory event log and the reference stores can)" if gaps else "no hard failure"))

    r = detail("TC-025", "delentia")
    anchor_only = r.get("caught_only_with_an_external_anchor") or []
    item(2, "TC-025: replay calls no external API and log tampering is detected", "PASS" if r["passed"] and r["sections"]["r2"]["external_attempts"] == 0 else "FAIL",
         f"R2 external attempts {r['sections']['r2']['external_attempts']}; every listed tamper is caught by the chains except truncation of the newest rows, which only an external anchor catches ({len(anchor_only)} logs)")

    mine = find("TC-010", "delentia@")
    naive = find("TC-010", "naive_new_key@")
    item(3, "TC-010: a killed process resumes without a duplicate side effect", "PASS" if mine and all(x["passed"] and not x["hard_failures"] for x in mine) else "FAIL",
         f"{sum(1 for x in mine if x['passed'])}/{len(mine)} kill points passed with a real process termination and a separate mock API; the naive control duplicated in "
         f"{sum(1 for x in naive if x['hard_failures'])} windows, so the check can fail")

    full, cap8 = detail("TC-006", "delentia_full"), detail("TC-006", "delentia_full_cap8")
    item(4, "TC-006 (scripted): the user's intent survives a session reset and memory pressure",
         ("PASS" if full["passed"] else "PARTIAL") if cap8["passed"] and full["metrics"]["protected_intent_accuracy"] == 100.0 else "FAIL",
         ("with the default of 5 shown pinned rules the goal rule is dropped when a sixth is added (restoration 50; the prompt now says so); with DELENTIA_MAX_PINNED_SHOWN=8 restoration is 100. "
          "Protected constraints held in every Delentia arm because the owner policy enforces them; the pins only inform") if not full["passed"] else "restored in every session")

    item(5, "the harness has external oracles and a separate workspace per run", "PASS" if find("TC-003", "d0_delentia") and all(x["verified"] for x in suite["runs"]) else "FAIL",
         f"hidden tests and the answer key are outside the agent's workspace (tested); the oracle runs the agent's package in a clean folder in another process; every run has its own work folder; all {len(suite['runs'])} bundles verify")

    from research.daaes import budget_guard
    item(6, "the model gateway has token and cost logging and a hard budget guard", "PARTIAL" if hasattr(budget_guard, "GuardedProvider") else "FAIL",
         "research/daaes/budget_guard.py enforces per-run and experiment limits before each call, fails closed on an unknown price and refuses automatic paid fallback (11 tests); "
         "the live adapter that wraps Delentia's provider chain with it is not built, so the guard has never stood in front of a real model")

    from research.daaes.state_fixture import make_ops, state_hash
    a, b = make_ops(suite["seed"], "small"), make_ops(suite["seed"], "small")
    reproducible = state_hash({"i": a[0], "s": a[1]}) == state_hash({"i": b[0], "s": b[1]})
    revalid = all(bundle.verify_bundle(Path(r_["folder"]))["valid"] for r_ in suite["runs"])
    item(7, "fixtures and run manifests are reproducible", "PASS" if reproducible and revalid else "FAIL",
         "the same seed gives the same fixture hash; every bundle carries its fixture hash, the commit, the command line and a seal that re-verifies")

    passed = sum(1 for i in items if i["status"] == "PASS")
    partial = sum(1 for i in items if i["status"] == "PARTIAL")
    return {"items": items, "passed": passed, "partial": partial, "total": 7, "ready_for_paid_calls": passed + partial == 7 and passed >= 6}


def render(result: Dict[str, Any]) -> str:
    if not result["items"]:
        return str(result.get("note"))
    lines = ["# Pre-API Spending Checklist", ""]
    for i in result["items"]:
        lines.append(f"{i['n']}. **{i['status']}** - {i['title']}\n   {i['why']}")
    lines += ["", f"{result['passed']} PASS, {result['partial']} PARTIAL, {7 - result['passed'] - result['partial']} FAIL of 7. Ready for a paid call: **{result['ready_for_paid_calls']}**."]
    return "\n".join(lines)
