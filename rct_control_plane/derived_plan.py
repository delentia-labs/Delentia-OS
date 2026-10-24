"""Model-free, criterion-derived plans. No inference of facts or tool authority.

This compiler supplies inspectable prerequisites and checks for the four
supported predicates. It deliberately does not claim arbitrary semantic RCT-7.
"""
from __future__ import annotations

DERIVE_REQUEST = {"derive_from_criteria": True}
RULESET = "criterion-prerequisites-1"


def derive_context(goal: str, criteria: list[dict]) -> dict:
    facts = [{"id": "goal", "text": goal[:4000], "source": "user_goal (reported intent, not verified fact)"}]
    components = []
    for criterion in criteria:
        cid, kind, value = criterion["id"], criterion["kind"], criterion["value"]
        fact_id = f"predicate_{cid}"
        facts.append({"id": fact_id, "text": f"{kind}: {value}", "source": f"acceptance_criteria:{cid}"})
        if kind == "file_unchanged":
            description = f"Preserve original bytes of workspace file {value}; no write permission is granted."
            output = f"Original SHA-256 and final observed SHA-256 for {value}"
        elif kind == "contains":
            description = "Prepare requested literal text; distinguish inclusion from factual support."
            output = f"Answer containing the user-requested literal: {value}"
        elif kind == "language":
            description = f"Prepare answer using requested {value} script; script detection does not assess fluency."
            output = f"Answer with {value} script"
        else:
            description = "Serialize the answer as one JSON object; parseability does not certify its contents."
            output = "JSON object answer"
        components.append({"id": f"prepare_{cid}", "action": "transform_answer", "description": description,
                           "input_facts": ["goal", fact_id], "outputs": [output], "criteria": []})
        components.append({"id": f"check_{cid}", "action": "compare",
                           "description": f"Evaluate {kind} using the existing deterministic contract comparator.",
                           "input_facts": [fact_id], "depends_on": [f"prepare_{cid}"],
                           "outputs": [f"Observed pass or difference for {cid}"], "criteria": [cid]})
    return {"schema_version": 1, "facts": facts, "unknowns": [],
            "assumptions": ["Explicit predicates are necessary checks, not a complete definition of semantic success."],
            "components": components}


def annotate(plan: dict) -> None:
    plan["planning_origin"] = "criterion_derived"
    plan["derivation"] = {"ruleset": RULESET, "model_calls": 0, "evidence_status": "user_reported",
                          "semantic_completeness": False}
    plan["limitations"] = ("Criterion-derived prerequisites only. No inferred source truth, critical unknown discovery, "
                           "arbitrary semantic decomposition, write authorization or model capability claim.")
