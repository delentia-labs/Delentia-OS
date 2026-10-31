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

from pydantic import Field, TypeAdapter

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


class CriterionVerification(PlanItem):
    """Typed verifier statement; the scheduler binds it to its declared criterion.

    This records a trusted handler's verdict, not independent source truth.
    """
    criterion_id: str = Field(min_length=1, max_length=80)
    satisfied: bool


class VerificationRejected(ValueError):
    def __init__(self, criterion_id: str, observed: dict):
        super().__init__(f"criterion {criterion_id} was not verified")
        self.criterion_id = criterion_id
        self.expected = {"criterion_id": criterion_id, "satisfied": True}
        self.observed = copy.deepcopy(observed)


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
        if node.phase != "observation" and not callable(handler.run):
            raise ValueError("compute/verify handlers require an implementation")
        if node.phase == "observation" and handler.run is not None:
            raise ValueError("observation handlers must use governed dispatch")
        for port, value in node.parameters.items():
            TypeAdapter(fields[port].rebuild_annotation()).validate_python(value, strict=True)
        if not node.inputs:
            handler.input_model.model_validate(node.parameters)
        if node.criteria:
            if node.phase != "verify" or len(node.criteria) != 1:
                raise ValueError("each verifier node must bind exactly one criterion")
            if not issubclass(handler.output_model, CriterionVerification):
                raise ValueError("criterion handlers require typed verification output")
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
        self._registry = MappingProxyType(dict(registry))
        self._criterion_ids = frozenset(criterion_ids)
        self._program = validate_program(copy.deepcopy(program), self._registry, self._criterion_ids, answers)
        self._nodes = {n.id: n for n in self._program.nodes}
        self._answers = copy.deepcopy(answers)
        self._outputs = {}
        self._verified = set()
        self._in_progress = set()
        self._failed = None
        self.on_complete = on_complete

    @property
    def failed(self):
        return self._failed

    @property
    def registry(self):
        return self._registry

    @property
    def program(self):
        return self._program.model_copy(deep=True)

    @property
    def nodes(self):
        return {key: node.model_copy(deep=True) for key, node in self._nodes.items()}

    @property
    def answers(self):
        return copy.deepcopy(self._answers)

    @property
    def outputs(self):
        return copy.deepcopy(self._outputs)

    def ready(self, node):
        node = self._nodes[node.id]
        return (node.id not in self._outputs and node.id not in self._in_progress and not self._failed
                and set(node.depends_on) <= self._outputs.keys()
                and all(self._answers.get(key) for key in node.requires))

    def _commit_output(self, node, output):
        validated = self._registry[node.handler].output_model.model_validate(output).model_dump()
        if node.criteria:
            criterion = node.criteria[0]
            if (not isinstance(output, dict) or output.get("criterion_id") != criterion
                    or output.get("satisfied") is not True
                    or validated.get("criterion_id") != criterion or validated.get("satisfied") is not True):
                raise VerificationRejected(criterion, output if isinstance(output, dict) else validated)
        self.on_complete(node.id, copy.deepcopy(validated))
        self._outputs[node.id] = copy.deepcopy(validated)
        self._verified.update(node.criteria)

    def record(self, key, output):
        node = self._nodes[key]
        if not self.ready(node):
            raise ValueError("component prerequisites not completed or critical input unavailable")
        self._in_progress.add(key)
        try:
            self._commit_output(node, output)
        except Exception:
            self._failed = key
            raise
        finally:
            self._in_progress.discard(key)

    def observe(self, key, output):
        if self._nodes[key].phase != "observation":
            raise ValueError("only observation nodes accept dispatched evidence")
        self.record(key, output)

    def drain(self, phase):
        if self._failed:
            raise ValueError("failed execution requires reconciliation")
        count = 0
        while True:
            node = next((n for n in self._program.nodes if n.phase == phase and self.ready(n)), None)
            if node is None:
                return count
            self._in_progress.add(node.id)
            try:
                handler = self._registry[node.handler]
                if handler.run is None or phase == "observation":
                    raise ValueError("observations require governed dispatch")
                payload = copy.deepcopy(node.parameters)
                payload.update({port: copy.deepcopy(self._outputs[parent]) for port, parent in node.inputs.items()})
                inputs = handler.input_model.model_validate(payload)
                self._commit_output(node, handler.run(inputs))
                count += 1
            except Exception:
                self._failed = node.id
                raise
            finally:
                self._in_progress.discard(node.id)

    def require_complete(self):
        if (self._failed or self._in_progress or set(self._outputs) != set(self._nodes)
                or self._verified != self._criterion_ids):
            raise ValueError("not all planned components and criteria completed")
