"""Trusted budget handlers compiled into the shared typed execution DAG."""
from __future__ import annotations

import json
import re
from decimal import Context, Decimal, localcontext
from typing import Literal

from rct_control_plane.component_execution import Handler, validate_program
from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.verified_budget import Quote


class EmptyInput(PlanItem):
    pass


class SourceObservation(PlanItem):
    evidence_status: Literal["observed_bytes"]
    relative_path: str
    sha256: str
    tool_result_sha256: str
    quote: Quote


class BudgetInput(PlanItem):
    source: SourceObservation
    budget: str


class BudgetReport(PlanItem):
    quote_total: str
    budget_limit: str
    currency: Literal["THB", "USD", "EUR"]
    remaining: str
    within_budget: bool
    source: str
    evidence_sha256: str


class ReportInput(PlanItem):
    report: BudgetReport


class CriterionInput(ReportInput):
    criterion_id: str


class CriterionResult(PlanItem):
    criterion_id: str
    satisfied: Literal[True]


def compare_budget(inputs):
    from rct_control_plane.semantic_plan import validate_budget
    budget, source = inputs.budget, inputs.source
    validate_budget(budget)
    currency = re.search(r"THB|USD|EUR|บาท", budget, re.I)[0].upper().replace("บาท", "THB")
    limit = Decimal(re.sub(r"THB|USD|EUR|บาท", "", budget, flags=re.I).strip().replace(",", ""))
    if source.quote.currency != currency:
        raise ValueError("currency mismatch; no implicit FX conversion")
    total = Decimal(source.quote.total)
    with localcontext(Context(prec=40)):
        return {"quote_total": format(total, ".2f"), "budget_limit": format(limit, ".2f"),
                "currency": currency, "remaining": format(limit - total, ".2f"), "within_budget": total <= limit,
                "source": source.relative_path, "evidence_sha256": source.sha256}


def registry_for(plan):
    def check(inputs):
        from rct_control_plane.intent_contract import compare
        differences = compare(plan, json.dumps(inputs.report.model_dump(), ensure_ascii=False))
        if any(d["criterion_id"] == inputs.criterion_id for d in differences):
            raise ValueError(f"criterion {inputs.criterion_id} not satisfied")
        return {"criterion_id": inputs.criterion_id, "satisfied": True}
    return {
        "quote.observe.v1": Handler(EmptyInput, SourceObservation, "observation", None),
        "budget.compare.v1": Handler(BudgetInput, BudgetReport, "compute", compare_budget),
        "report.copy.v1": Handler(ReportInput, BudgetReport, "verify", lambda i: i.report.model_dump()),
        "criterion.check.v1": Handler(CriterionInput, CriterionResult, "verify", check),
    }


def compile_program(plan):
    """Trusted compiler: descriptions/criteria cannot register arbitrary code."""
    from rct_control_plane.intent_contract import IntentContractError
    criterion_ids = {c["id"] for c in plan["criteria"]}
    answers = {u["id"]: u["answer"] for u in plan["unknowns"]}
    expected = {"inspect_sources", "compare_budget", "compose_answer"}
    expected |= {f"{prefix}_{cid}" for cid in criterion_ids for prefix in ("prepare", "check")}
    if {n["id"] for n in plan["components"]} != expected or len(plan["components"]) != len(expected):
        raise IntentContractError("unsupported verified-budget component inventory")
    nodes = []
    for component in plan["components"]:
        key = component["id"]
        node = {"id": key, "depends_on": component["depends_on"], "requires": component["requires"],
                "criteria": component["criteria"], "parameters": {}, "inputs": {}}
        if key == "inspect_sources":
            node.update(handler="quote.observe.v1", phase="observation")
        elif key == "compare_budget":
            node.update(handler="budget.compare.v1", phase="compute", inputs={"source": "inspect_sources"},
                        parameters={"budget": answers.get("budget") or ""})
        elif key == "compose_answer" or key.startswith("prepare_"):
            node.update(handler="report.copy.v1", phase="verify",
                        inputs={"report": "compare_budget" if key == "compose_answer" else "compose_answer"})
        else:
            cid = key.removeprefix("check_")
            if component["criteria"] != [cid]:
                raise IntentContractError("criterion verifier binding differs from component")
            node.update(handler="criterion.check.v1", phase="verify", inputs={"report": f"prepare_{cid}"},
                        parameters={"criterion_id": cid})
        nodes.append(node)
    value = {"schema_version": 1, "nodes": nodes}
    try:
        return validate_program(value, registry_for(plan), criterion_ids, answers).model_dump()
    except ValueError as exc:
        raise IntentContractError("invalid typed execution plan") from exc


def validate_executor(plan):
    from rct_control_plane.intent_contract import IntentContractError
    executor = plan.get("semantic_planning", {}).get("executor")
    if executor is None:
        if "execution_program" in plan:
            raise IntentContractError("execution program has no supported executor")
        return
    if executor != "verified_budget_v1":
        raise IntentContractError("unsupported executor version; fallback refused")
    compiled = compile_program(plan)
    # Existing sealed v1 plans without this optional IR remain valid. New plans
    # carry it in their plan digest; a mismatched IR never silently falls back.
    if "execution_program" in plan and plan["execution_program"] != compiled:
        raise IntentContractError("execution program differs from compiled plan")
