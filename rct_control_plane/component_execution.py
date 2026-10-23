"""Typed, bounded DAG execution for trusted read-only handler registries.

This module grants no tool authority. Observations arrive from the governed
dispatcher; handlers are registered by application code, never by a request.
No automatic recovery/retry of a running contract is provided here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Literal

from pydantic import Field

from rct_control_plane.rct_plan import PlanItem


class ExecutionNode(PlanItem):
    id: str = Field(min_length=1, max_length=80)
    handler: str = Field(min_length=1, max_length=100)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    inputs: dict[str, str] = Field(default_factory=dict)
    parameters: dict = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list, max_length=50)
    criteria: list[str] = Field(default_factory=list, max_length=20)
    phase: Literal["observation", "compute", "verify"]


class ExecutionProgram(PlanItem):
    schema_version: Literal[1] = 1
    nodes: list[ExecutionNode] = Field(min_length=1, max_length=50)


@dataclass(frozen=True)
class Handler:
    input_model: type[PlanItem]
    output_model: type[PlanItem]
    phase: Literal["observation", "compute", "verify"]
    run: Callable[[PlanItem], dict] | None


def validate_program(program, registry, criterion_ids, unknown_ids):
    """Check topology, typed edges and complete criterion verifier coverage."""
    if not isinstance(program, dict) or type(program.get("schema_version")) is not int:
        raise ValueError("execution schema version must be an integer")
    parsed = ExecutionProgram.model_validate(program)
    nodes = {n.id: n for n in parsed.nodes}
    if len(nodes) != len(parsed.nodes):
        raise ValueError("duplicate execution node")
    covered = []
    for node in nodes.values():
        handler = registry.get(node.handler)
        if handler is None or handler.phase != node.phase:
            raise ValueError("unsupported execution handler or phase")
        if len(set(node.depends_on)) != len(node.depends_on):
            raise ValueError("duplicate execution dependency")
        if set(node.depends_on) - nodes.keys() or set(node.requires) - set(unknown_ids):
            raise ValueError("dangling execution dependency or unknown")
        if set(node.inputs.values()) - set(node.depends_on):
            raise ValueError("typed inputs require explicit dependency edges")
        fields = handler.input_model.model_fields
        if set(node.inputs) & set(node.parameters) or set(node.inputs) | set(node.parameters) != set(fields):
            raise ValueError("handler inputs must match the declared schema")
        # References carry whole typed outputs, not unvalidated dotted lookups.
        for port, parent in node.inputs.items():
            upstream = registry.get(nodes[parent].handler)
            if upstream is None or fields[port].annotation is not upstream.output_model:
                raise ValueError("incompatible handler input/output edge")
        if node.criteria and node.phase != "verify":
            raise ValueError("criteria must be assigned to verification handlers")
        covered.extend(node.criteria)
    if set(covered) != set(criterion_ids) or len(covered) != len(set(covered)):
        raise ValueError("each criterion requires exactly one verifier")
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError("execution dependency cycle")
        if key not in visited:
            visiting.add(key)
            for parent in nodes[key].depends_on:
                visit(parent)
            visiting.remove(key)
            visited.add(key)
    for key in nodes:
        visit(key)
    return parsed


class ComponentScheduler:
    """One claim, bounded nodes, typed outputs and receipt-before-completion.

    on_complete persists/records an output before it becomes available to
    descendants. The surrounding governed loop owns durable CAS transitions.
    A failure is sticky; callers must reconcile rather than retry this instance.
    """
    def __init__(self, program, registry, criterion_ids, answers, on_complete):
        self.registry = MappingProxyType(dict(registry))
        self.program = validate_program(program, self.registry, criterion_ids, answers)
        self.nodes = {n.id: n for n in self.program.nodes}
        self.answers = copy.deepcopy(answers)
        self.outputs = {}
        self.failed = None
        self.on_complete = on_complete

    def ready(self, node):
        return (node.id not in self.outputs and not self.failed
                and set(node.depends_on) <= self.outputs.keys()
                and all(self.answers.get(key) for key in node.requires))

    def record(self, key, output):
        node = self.nodes[key]
        if not self.ready(node):
            raise ValueError("component prerequisites not completed or critical input unavailable")
        try:
            validated = self.registry[node.handler].output_model.model_validate(output).model_dump()
            self.on_complete(key, copy.deepcopy(validated))
            self.outputs[key] = copy.deepcopy(validated)
        except Exception:
            self.failed = key
            raise

    def observe(self, key, output):
        if self.nodes[key].phase != "observation":
            raise ValueError("only observation nodes accept dispatched evidence")
        self.record(key, output)

    def drain(self, phase):
        if self.failed:
            raise ValueError("failed execution requires reconciliation")
        count = 0
        while True:
            node = next((n for n in self.program.nodes if n.phase == phase and self.ready(n)), None)
            if node is None:
                return count
            try:
                handler = self.registry[node.handler]
                if handler.run is None or phase == "observation":
                    raise ValueError("observations require governed dispatch")
                payload = copy.deepcopy(node.parameters)
                payload.update({port: copy.deepcopy(self.outputs[parent]) for port, parent in node.inputs.items()})
                inputs = handler.input_model.model_validate(payload)
                self.record(node.id, handler.run(inputs))
                count += 1
            except Exception:
                self.failed = node.id
                raise

    def require_complete(self):
        if self.failed or set(self.outputs) != set(self.nodes):
            raise ValueError("not all planned components completed")
