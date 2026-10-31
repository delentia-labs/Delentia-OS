"""Application-owned necessary conditions for opt-in typed intent plans.

Checks dataflow, not source truth or semantic completeness. Callers must supply
reviewed rules, never accept a request/model's rules as execution authority.
No scheduling, approval, persistence or provider calls occur here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rct_control_plane.component_execution import ExecutionProgram, Handler
from rct_control_plane.typed_intent import GroundedIntent, validate_intent_program


@dataclass(frozen=True)
class NecessaryCondition:
    """Require a trusted producer on the verifier's actual typed input path."""
    id: str
    producer_handlers: frozenset[str]


@dataclass(frozen=True)
class CriterionCapability:
    verifier_handlers: frozenset[str]
    conditions: tuple[NecessaryCondition, ...]


def validate_conditioned_program(
    intent: GroundedIntent,
    program: dict,
    registry: Mapping[str, Handler],
    answers: dict,
    capabilities: Mapping[str, CriterionCapability],
) -> ExecutionProgram:
    """Fail closed when any obligation lacks an application-owned capability.

    All conditions are conjunctive; producer alternatives within one condition
    are disjunctive. Ordering edges alone do not demonstrate consumed evidence.
    A successful return is structural validation, never an approval to execute.
    """
    parsed = validate_intent_program(intent, program, registry, answers)
    criteria = {c.id for c in [*intent.proposal.material_criteria, *intent.proposal.constraints]}
    if set(capabilities) != criteria:
        raise ValueError("every obligation needs an explicit capability")
    nodes = {n.id: n for n in parsed.nodes}

    def input_ancestors(key: str) -> set[str]:
        found: set[str] = set()
        pending = list(nodes[key].inputs.values())
        while pending:
            parent = pending.pop()
            if parent not in found:
                found.add(parent)
                pending.extend(nodes[parent].inputs.values())
        return found

    for node in parsed.nodes:
        if not node.criteria:
            continue
        capability = capabilities[node.criteria[0]]
        if not capability.verifier_handlers or any(
            name not in registry or registry[name].phase != "verify"
            for name in capability.verifier_handlers
        ):
            raise ValueError("capability references unsupported verifier")
        if node.handler not in capability.verifier_handlers:
            raise ValueError("criterion uses an incompatible verifier")
        condition_ids = [c.id for c in capability.conditions]
        if any(not key.strip() for key in condition_ids) or len(set(condition_ids)) != len(condition_ids):
            raise ValueError("condition identities must be nonempty and unique")
        upstream_handlers = {nodes[key].handler for key in input_ancestors(node.id)}
        for condition in capability.conditions:
            if not condition.producer_handlers or any(
                name not in registry or registry[name].phase == "verify"
                for name in condition.producer_handlers
            ):
                raise ValueError("condition references unsupported producer")
            if not upstream_handlers.intersection(condition.producer_handlers):
                raise ValueError(f"necessary condition is not consumed: {condition.id}")
    return parsed
