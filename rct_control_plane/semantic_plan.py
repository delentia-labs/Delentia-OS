"""Bounded bilingual task planner, not an unrestricted semantic reasoner.

Rules infer task dependencies, not source truth, prices or tool authority.
All supplied facts remain reported; unsupported/ambiguous goals fail closed.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from pydantic import Field, ValidationError
from decimal import Decimal

from rct_control_plane.derived_plan import derive_context
from rct_control_plane.rct_plan import Fact, PlanItem

RULESET = "bilingual-summary-budget-1"


def validate_budget(value: str) -> None:
    """A generic acknowledgement is not a budget; currency must be explicit."""
    from rct_control_plane.intent_contract import IntentContractError
    number = r"(?:[1-9]\d{0,2}(?:,\d{3})+|0|[1-9]\d*)(?:\.\d{1,2})?"
    match = re.fullmatch(rf"(?:(THB|USD|EUR|บาท)\s*)?({number})\s*(THB|USD|EUR|บาท)?", value.strip(), re.I)
    if (not match or bool(match[1]) == bool(match[3])
            or not Decimal("0") < Decimal(match[2].replace(",", "")) <= Decimal("1e15")):
        raise IntentContractError("budget needs a positive amount and explicit currency: THB, USD, EUR or บาท")


class SemanticInput(PlanItem):
    facts: list[Fact] = Field(default_factory=list, max_length=20)
    budget: str | None = Field(default=None, min_length=1, max_length=4000)


def compile_request(goal: str, criteria: list[dict], value: object) -> tuple[dict, dict]:
    from rct_control_plane.intent_contract import IntentContractError
    if not isinstance(value, dict) or set(value) != {"semantic_plan"}:
        raise IntentContractError("semantic planning request has only semantic_plan")
    try:
        request = SemanticInput.model_validate(value["semantic_plan"])
    except ValidationError as exc:
        raise IntentContractError("invalid semantic planning input") from exc
    if len({fact.id for fact in request.facts}) != len(request.facts):
        raise IntentContractError("semantic fact ids must be unique")
    text = unicodedata.normalize("NFC", goal).casefold()
    summarize = re.search(r"สรุป|\bsummar(?:y|i[sz]e)\b", text)
    compare = re.search(r"เปรียบเทียบ|เทียบ|อยู่ในงบ|เกินงบ|\b(?:compare|within|afford)\b", text)
    budget = re.search(r"งบ|\b(?:budget|afford)\b", text)
    negated = re.search(r"(?:ไม่ต้อง|อย่า|ห้าม)\s*(?:เปรียบเทียบ|เทียบ|สรุป)|\b(?:do not|don't)\s+(?:compare|summari[sz]e)\b", text)
    if negated or (summarize and compare) or bool(summarize) == bool(compare and budget):
        raise IntentContractError("unsupported or ambiguous semantic goal; choose summary or budget comparison explicitly")
    task = "summary" if summarize else "budget_compare"
    if request.budget is not None:
        validate_budget(request.budget)
    context = derive_context(goal, criteria)
    source_ids = []
    provenance = []
    for i, fact in enumerate(request.facts):
        fid = f"source_{i + 1}"
        source_ids.append(fid)
        context["facts"].append({"id": fid, "text": fact.text, "source": fact.source})
        provenance.append({"fact_id": fid, "reported_id": fact.id, "status": "user_reported",
                           "source": fact.source, "text_sha256": hashlib.sha256(fact.text.encode()).hexdigest()})
    requires = []
    if not source_ids:
        context["unknowns"].append({"id": "source_text", "question": "ข้อมูลต้นทางที่จะสรุปหรือเทียบคืออะไร? / What source data should be used?",
                                   "critical": True, "answer": None})
        requires.append("source_text")
    components = [{"id": "inspect_sources", "action": "transform_answer",
        "description": "Inspect reported source data and distinguish its claims from verified observations.",
        "input_facts": source_ids, "requires": requires, "outputs": ["Source-linked claims and unresolved limitations"]}]
    dependency = "inspect_sources"
    if task == "budget_compare":
        context["unknowns"].append({"id": "budget", "question": "งบสูงสุดและสกุลเงินคืออะไร? / What is the budget limit and currency?",
                                   "critical": True, "answer": request.budget})
        components.append({"id": "compare_budget", "action": "compare",
            "description": "Identify quoted totals, currency, scope and exclusions; compare with the confirmed budget. Do not invent missing amounts or assume currencies match.",
            "input_facts": source_ids, "requires": ["budget"], "depends_on": [dependency],
            "outputs": ["Budget assessment with source references; unresolved totals/currency remain explicit"]})
        dependency = "compare_budget"
    components.append({"id": "compose_answer", "action": "transform_answer",
        "description": "Summarize reported claims with source attribution." if task == "summary" else "Explain the budget comparison and its evidence limitations.",
        "input_facts": source_ids, "depends_on": [dependency], "outputs": ["Answer for the selected task"]})
    for component in context["components"]:
        if component["id"].startswith("prepare_"):
            component["depends_on"] = ["compose_answer"]
    context["components"] = components + context["components"]
    context["assumptions"].append("Task classification and dependency rules are bounded in scope; reported facts are not independently verified.")
    metadata = {"ruleset": RULESET, "task": task, "model_calls": 0, "semantic_completeness": False,
                "goal_sha256": hashlib.sha256(goal.encode()).hexdigest(),
                "classification": {"status": "rule_inferred", "matched_text": (summarize if summarize else compare).group()},
                "sources": provenance,
                "limitations": ["No general semantic inference, verified-source acquisition or automatic discovery of every missing price/currency/scope detail.",
                                "Final success still uses declared predicates and heuristic grounding, not a semantic budget oracle."]}
    return context, metadata


def annotate(plan: dict, metadata: dict) -> None:
    plan["planning_origin"] = "bounded_semantic_rules"
    plan["semantic_planning"] = metadata
    plan["limitations"] = "Bounded summary/budget task rules; source claims are reported, not verified. No general semantic RCT-7 or effect authorization."


def context_from_plan(plan: dict) -> dict:
    return {"schema_version": 1, **{key: plan[key] for key in ("facts", "unknowns", "assumptions", "components")}}
