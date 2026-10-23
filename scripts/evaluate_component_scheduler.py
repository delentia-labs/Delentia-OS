"""Paired offline execution A/B; not an LLM or general RCT accuracy benchmark."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rct_control_plane.intent_contract import build_plan, plan_digest, validate_criteria
from rct_control_plane.verified_budget import BudgetPipeline

BASELINE = "26139b01a8bdd2b6d3d569c9a955db990e64d163"


def money(cents):
    return ("-" if cents < 0 else "") + f"{abs(cents)//100}.{abs(cents)%100:02d}"


def evaluate():
    source = subprocess.check_output(["git", "show", f"{BASELINE}:rct_control_plane/verified_budget.py"], cwd=ROOT, text=True)
    baseline = types.ModuleType("recorded_budget_baseline")
    sys.modules[baseline.__name__] = baseline
    exec(compile(source, "recorded_budget_baseline.py", "exec"), baseline.__dict__)
    rows = []
    with tempfile.TemporaryDirectory(prefix="delentia-ab-") as directory:
        root = Path(directory)
        for cohort in ("canonical", "reordered", "invalid_evidence"):
            for i in range(24):
                limit = 10000+i*317; total = limit+(-101, 0, 1, 271)[i%4]
                currency = ("THB", "USD", "EUR")[i%3]
                value = {"schema_version": 1, "total": money(total), "currency": currency, "total_is_final": True}
                if cohort == "invalid_evidence":
                    if i%3 == 0: value["total_is_final"] = False
                    elif i%3 == 1: value["currency"] = "USD" if currency != "USD" else "EUR"
                    else: value["total"] = "invented"
                raw = json.dumps(value, separators=(",", ":")).encode()
                (root/"quote.json").write_bytes(raw); sha = hashlib.sha256(raw).hexdigest()
                criteria = validate_criteria([{"kind": "json_object"}, {"kind": "file_unchanged", "value": "quote.json"}])
                plan = build_plan("เทียบราคากับงบ" if i%2 else "Compare quote with budget", criteria, root,
                    {"semantic_plan": {"budget": money(limit)+" "+currency, "quote_evidence": {"relative_path": "quote.json", "sha256": sha}}})
                if cohort == "reordered":
                    from rct_control_plane.budget_execution import compile_program
                    plan["components"].reverse(); plan["execution_program"] = compile_program(plan)
                expected = {"quote_total": money(total), "budget_limit": money(limit), "currency": currency,
                    "remaining": money(limit-total), "within_budget": total <= limit, "source": "quote.json", "evidence_sha256": sha}
                row = {"case": f"{cohort}-{i}", "cohort": cohort, "language": "th" if i%2 else "en", "outcomes": {}}
                pairs = [("A", baseline.BudgetPipeline), ("B", BudgetPipeline)]
                if i%2: pairs.reverse()
                for name, cls in pairs:
                    durations, outcomes = [], []
                    for _ in range(3):
                        contract = {"id": f"ab-{i}", "version": 1, "plan": copy.deepcopy(plan), "plan_sha256": plan_digest(plan)}
                        start = time.perf_counter_ns(); pipeline = cls(contract, "paired-ab")
                        pipeline.observe("delentia_read_repo_file", {"relative_path": "quote.json"},
                            {"path": "quote.json", "truncated": False, "content_text": raw.decode()})
                        accepted = not pipeline.finish(pipeline.decision()["final_answer"], [])
                        durations.append((time.perf_counter_ns()-start)/1e6)
                        correct = accepted and pipeline.report == expected if cohort != "invalid_evidence" else not accepted
                        outcomes.append((accepted, correct))
                    assert len(set(outcomes)) == 1
                    row["outcomes"][name] = {"accepted": outcomes[0][0], "correct": outcomes[0][1], "median_ms": statistics.median(durations)}
                rows.append(row)
    aggregate = {}
    for cohort in ("canonical", "reordered", "invalid_evidence"):
        selected = [r for r in rows if r["cohort"] == cohort]
        aggregate[cohort] = {name: {"correct": sum(r["outcomes"][name]["correct"] for r in selected), "cases": len(selected),
            "median_ms": statistics.median(r["outcomes"][name]["median_ms"] for r in selected)} for name in ("A", "B")}
    return {"baseline_sha": BASELINE, "baseline_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "scope": "Paired offline execution regression on local files; no governed dispatch, persistence or model in this microbenchmark.",
        "method": "72 generated cases, 3 timing repeats per arm, alternating arm order; integer-cent oracle. Reordered cohort is structural stress, not holdout. Repeats are not independent samples.",
        "not_claimed": ["general RCT accuracy", "model capability", "production latency", "unattended readiness"],
        "aggregate": aggregate, "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = evaluate()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(result["aggregate"], indent=2))
    if any(not r["outcomes"]["B"]["correct"] for r in result["rows"]): raise SystemExit(1)
