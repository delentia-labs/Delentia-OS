"""Inspectable user-declared planning context, not inferred model reasoning.

Facts are reported by their source, not certified true by schema validation.
Component descriptions never grant tools, approval or policy authority.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Fact(PlanItem):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    text: str = Field(min_length=1, max_length=4000)
    source: str = Field(min_length=1, max_length=2000)


class Unknown(PlanItem):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    question: str = Field(min_length=1, max_length=2000)
    critical: bool = False
    answer: str | None = Field(default=None, min_length=1, max_length=4000)


class Component(PlanItem):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    action: Literal["read", "transform_answer", "compare"]
    description: str = Field(min_length=1, max_length=2000)
    input_facts: list[str] = Field(default_factory=list, max_length=50)
    requires: list[str] = Field(default_factory=list, max_length=50)
    outputs: list[str] = Field(min_length=1, max_length=20)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    criteria: list[str] = Field(default_factory=list, max_length=20)


class PlanningContext(PlanItem):
    schema_version: Literal[1] = 1
    facts: list[Fact] = Field(default_factory=list, max_length=50)
    unknowns: list[Unknown] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    components: list[Component] = Field(min_length=1, max_length=50)


def validate_context(value: object, criterion_ids: set[str]) -> dict:
    from rct_control_plane.intent_contract import IntentContractError
    try:
        context = PlanningContext.model_validate(value)
    except ValidationError as exc:
        raise IntentContractError("invalid planning_context schema") from exc
    groups = [context.facts, context.unknowns, context.components]
    ids = [[item.id for item in group] for group in groups]
    if any(len(group) != len(set(group)) for group in ids):
        raise IntentContractError("planning ids must be unique within each group")
    facts, unknowns, components = map(set, ids)
    covered = set()
    graph = {}
    for component in context.components:
        if (set(component.input_facts) - facts or set(component.requires) - unknowns
                or set(component.depends_on) - components or set(component.criteria) - criterion_ids):
            raise IntentContractError("planning component has a dangling reference")
        if any(not text.strip() or len(text) > 2000 for text in component.outputs):
            raise IntentContractError("component outputs must be nonempty bounded text")
        graph[component.id] = component.depends_on
        covered.update(component.criteria)
    if covered != criterion_ids:
        raise IntentContractError("every criterion must be assigned to a planning component")
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            raise IntentContractError("planning dependency cycle")
        if node not in done:
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            done.add(node)
    for node in graph:
        visit(node)
    if any(not text.strip() or len(text) > 2000 for text in context.assumptions):
        raise IntentContractError("assumptions must be nonempty bounded text")
    return context.model_dump()


def apply_context(plan: dict, context: dict) -> None:
    plan.update(plan_schema_version=2, planning_origin="user_declared", facts=context["facts"],
                unknowns=context["unknowns"], assumptions=context["assumptions"], components=context["components"])
    for condition in plan["backward_chain"]["necessary_conditions"]:
        condition["components"] = [component for component in context["components"]
                                   if condition["criterion_id"] in component["criteria"]]
        # Include transitive prerequisites, not just the last comparison node.
        by_id = {component["id"]: component for component in context["components"]}
        required = set()
        def include(node):
            if node not in required:
                required.add(node)
                for dependency in by_id[node]["depends_on"]:
                    include(dependency)
        for component in condition["components"]:
            include(component["id"])
        condition["prerequisites"] = [component for component in context["components"] if component["id"] in required]
    plan["clarification_questions"] = [{"id": u["id"], "question": u["question"]}
                                      for u in context["unknowns"] if u["critical"] and not u["answer"]]
    plan["limitations"] = "User-declared evidence and dependency graph, structurally validated; not an automatic semantic planner or truth oracle."
