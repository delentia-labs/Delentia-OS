"""
The thirty DAAES test cases (Research-01, section 6.1) and where each stands today. A status is a claim about EVIDENCE that exists in this repository, and a test checks that the files named exist.

  scripted_proven   the mechanism is exercised by a case with an independent oracle and a scripted model (zero cost); no claim about a language model
  partly            some of the case is covered (named), the rest is not
  existing_battery  an older measurement exists outside DAAES (named); it is not in the DAAES evidence format yet
  designed          a specification or fixture design exists; nothing runs yet
  needs_model       the case needs a capable model (the live pilot) and has no scripted stand-in that would mean anything
  needs_host        the case needs a host that runs for days, a witness, or users

L = autonomy level (Research-01 section 3.1, L0-L6), P = priority (P0 proves the architecture's core). Hermes: every case is `not_evaluated` until a pinned Hermes adapter exists.
"""
from __future__ import annotations

from typing import Any, Dict, List

T = "rct_control_plane/tests/"
CASES: List[Dict[str, Any]] = [
    {"id": "TC-001", "name": "Basic Tool Selection", "L": "L1", "P": "P0", "status": "existing_battery", "evidence": ["scripts/k1_5_formal_acceptance.py"], "needs": "a capable model (local 7B: 3 of 5 simple goals)"},
    {"id": "TC-002", "name": "Multi-Step File Processing", "L": "L2", "P": "P0", "status": "partly", "evidence": ["research/generate_ops.py", T + "test_research_ops_domain_round82_real.py"], "needs": "12 shapes of office work are graded with a scripted model; a real model has not run them"},
    {"id": "TC-003", "name": "Bug Fix + Regression", "L": "L3", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc003.py", T + "test_daaes_tc003_round83_real.py"], "needs": "a capable model to find the fixes (live pilot C4)"},
    {"id": "TC-004", "name": "Tool Timeout Recovery", "L": "L3", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc003.py"], "needs": "faults F1-F3 on the runner tool, recovery scored; a model's decision quality is the live part"},
    {"id": "TC-005", "name": "Failed API Fallback", "L": "L3", "P": "P0", "status": "partly", "evidence": [T + "test_provider_fallback_round57_real.py", "research/daaes/tc010.py"], "needs": "model fallback and API reconciliation are tested apart; not one scenario"},
    {"id": "TC-006", "name": "Goal Continuity Across Sessions", "L": "L5", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc006.py", T + "test_daaes_tc006_round83_real.py"], "needs": "whether a live model keeps the goal on its own (live pilot C3)"},
    {"id": "TC-007", "name": "Conflicting User Instructions", "L": "L5", "P": "P0", "status": "partly", "evidence": ["research/daaes/tc006.py", "research/daaes/tc007_tc020.py", T + "test_constraints_outside_retrieval_round82_real.py", T + "test_daaes_tc007_tc020_round84_real.py"], "needs": "scripted (Round 84): a rule in the owner policy binds a second person, a rule pinned in one person's memory does not; a live model's handling of two people disagreeing is not measured"},
    {"id": "TC-008", "name": "Memory Retrieval Accuracy", "L": "L5", "P": "P0", "status": "existing_battery", "evidence": ["research/recall_dataset_r70.py", T + "test_memory_recall_round69_real.py"], "needs": "held-out recall sets exist (English, Thai); not in the DAAES evidence format"},
    {"id": "TC-009", "name": "Memory Delta Reconstruction", "L": "L5", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc009.py", T + "test_daaes_tc009_round83_real.py"], "needs": "the Delta Engine's versioned log passes the whole matrix since Round 83; the way the engine was used until Round 82 fails it (pinned as an arm)"},
    {"id": "TC-010", "name": "Interrupted Task Recovery", "L": "L5", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc010.py", T + "test_daaes_tc010_round83_real.py"], "needs": "an agent loop that resumes a whole episode (today only the approval of an action is recoverable)"},
    {"id": "TC-011", "name": "Scheduled Research", "L": "L4", "P": "P1", "status": "partly", "evidence": [T + "test_cron_jobs_round57_real.py"], "needs": "the scheduler is tested; a research task on a schedule needs a model and time"},
    {"id": "TC-012", "name": "Daily Monitoring", "L": "L4", "P": "P1", "status": "needs_host", "evidence": ["scripts/autonomy_drill.py"], "needs": "a host that runs for days (the drill ran two minutes)"},
    {"id": "TC-013", "name": "Inventory Agent", "L": "L4-5", "P": "P1", "status": "designed", "evidence": ["research/daaes/SPECIFICATION.md"], "needs": "a 100-SKU, 30-day fixture; the ops inventory_join family is the small version"},
    {"id": "TC-014", "name": "Business Data Reconciliation", "L": "L3", "P": "P1", "status": "partly", "evidence": ["research/generate_ops.py"], "needs": "csv_totals / report_number / inventory_join families, scripted only"},
    {"id": "TC-015", "name": "Long-Horizon Project Planning", "L": "L5", "P": "P0", "status": "needs_model", "evidence": [T + "test_task_board_round60_real.py"], "needs": "the task board exists; planning quality is a model's"},
    {"id": "TC-016", "name": "Plan Revision Under Constraint", "L": "L5", "P": "P0", "status": "needs_model", "evidence": [T + "test_task_board_round60_real.py"], "needs": "replan exists; whether a model revises well is the live part"},
    {"id": "TC-017", "name": "Learning From Repeated Mistakes", "L": "L5", "P": "P0", "status": "needs_model", "evidence": ["research/PROTOCOL.md"], "needs": "arms M on/off are built in the research harness; they need a capable model"},
    {"id": "TC-018", "name": "Skill Reuse Across Sessions", "L": "L5", "P": "P1", "status": "partly", "evidence": [T + "test_warm_recall_round51_real.py"], "needs": "reuse is tested with a scripted model; learning a skill from a live episode is not"},
    {"id": "TC-019", "name": "Multi-Agent Delegation", "L": "L6", "P": "P1", "status": "scripted_proven", "evidence": ["scripts/full_pipeline_cases.py", T + "test_jitna_subagent_real.py"], "needs": "decomposition quality is a model's"},
    {"id": "TC-020", "name": "Multi-Agent Goal Conflict", "L": "L6", "P": "P0", "status": "partly", "evidence": [T + "test_jitna_subagent_real.py", "research/daaes/tc007_tc020.py", T + "test_daaes_tc007_tc020_round84_real.py"], "needs": "scripted (Round 84): a planner's plan is data, the legitimate step runs and the destructive and outbound steps are stopped when the folder is declared untrusted; with a live planner agent and a live developer agent it is not measured"},
    {"id": "TC-021", "name": "Permission Boundary", "L": "L3", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc003.py", "research/daaes/tc006.py"], "needs": "-"},
    {"id": "TC-022", "name": "Prompt Injection Resistance", "L": "L3", "P": "P0", "status": "scripted_proven", "evidence": ["scripts/measure_injection_defence.py", "research/daaes/tc006.py"], "needs": "an obedient scripted model only; a real model may behave differently"},
    {"id": "TC-023", "name": "Duplicate Action Prevention", "L": "L4", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc010.py", T + "test_crash_windows_round82_real.py"], "needs": "-"},
    {"id": "TC-024", "name": "Audit Trail Reconstruction", "L": "L5", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc025.py", T + "test_daaes_tc025_round83_real.py"], "needs": "truncation of the newest rows is caught only by an external anchor"},
    {"id": "TC-025", "name": "Replay Determinism", "L": "L5", "P": "P0", "status": "scripted_proven", "evidence": ["research/daaes/tc025.py", T + "test_daaes_tc025_round83_real.py"], "needs": "R4 (live re-execution) is variance, never byte identity"},
    {"id": "TC-026", "name": "Context Compression Retention", "L": "L5", "P": "P0", "status": "partly", "evidence": ["research/daaes/tc006.py", "scripts/measure_prompt_cost.py"], "needs": "pins survive 300 irrelevant memories; Delta v2 on tool output is measured for size, not for what a model can still answer"},
    {"id": "TC-027", "name": "Dynamic Web Workflow", "L": "L3", "P": "P1", "status": "designed", "evidence": [T + "test_browser_act_round62_real.py"], "needs": "a changing page fixture and a model"},
    {"id": "TC-028", "name": "Autonomous Incident Recovery", "L": "L4-5", "P": "P1", "status": "designed", "evidence": ["research/daaes/SPECIFICATION.md"], "needs": "Docker mock services and a host"},
    {"id": "TC-029", "name": "Long-Running Cost Control", "L": "L5", "P": "P1", "status": "scripted_proven", "evidence": ["research/daaes/budget_guard.py", T + "test_daaes_budget_guard_round83_real.py", T + "test_budget_reservation_round82_real.py"], "needs": "the guard has not stood in front of a real model"},
    {"id": "TC-030", "name": "End-to-End Autonomous Project", "L": "L6", "P": "P2", "status": "needs_model", "evidence": [], "needs": "everything above, a capable model and a host"},
]
STATUSES = ("scripted_proven", "partly", "existing_battery", "designed", "needs_model", "needs_host")


def counts() -> Dict[str, int]:
    out = {s: 0 for s in STATUSES}
    for c in CASES:
        out[c["status"]] += 1
    return out


def render() -> str:
    lines = ["# DAAES: the thirty cases and where each stands", "", "Generated from `research/daaes/catalogue.py`; a test checks that every evidence file exists. Hermes: every row is `not_evaluated` (no adapter yet).", "",
             "| id | case | L | P | status | evidence | what is still needed |", "|---|---|---|---|---|---|---|"]
    for c in CASES:
        lines.append(f"| {c['id']} | {c['name']} | {c['L']} | {c['P']} | {c['status']} | {', '.join('`' + e + '`' for e in c['evidence']) or '-'} | {c['needs']} |")
    n = counts()
    lines += ["", "Totals: " + ", ".join(f"{k} {v}" for k, v in n.items() if v) + f" ({len(CASES)} cases).", "",
              "`scripted_proven` is about the RUNTIME around a scripted model: it says nothing about what a language model would do with the same task."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    from pathlib import Path
    Path(__file__).with_name("CATALOGUE.md").write_text(render(), encoding="utf-8")
    print(counts())
