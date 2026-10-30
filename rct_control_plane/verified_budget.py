"""Read-only, dependency-enforced quote verifier. Document bytes are not vendor truth.

Receipts are local hash-linked working state, not signatures or off-host witnesses.
Only the governed read callback can supply evidence; generation is unnecessary.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from rct_control_plane.rct_plan import PlanItem

MAX_BYTES = 20000


def supports_verified_reads() -> bool:
    return os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")


class QuoteEvidence(PlanItem):
    relative_path: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Quote(PlanItem):
    schema_version: Literal[1]
    total: str = Field(max_length=20, pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$")
    currency: Literal["THB", "USD", "EUR"]
    total_is_final: bool


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("non-finite JSON constant")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def current_bytes(root: Path, relative: str) -> bytes:
    """Bounded POSIX read, refusing symlink components and non-regular files."""
    from rct_control_plane.intent_contract import _file
    _file(root, relative)  # workspace/secret-path policy, without reading contents
    parts = Path(relative).parts
    if any(part in {".", ".."} for part in parts) or not supports_verified_reads():
        raise ValueError("quote path/platform unavailable for verified reading")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor);descriptor = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        try:
            if not stat.S_ISREG(os.fstat(child).st_mode):
                raise ValueError("quote must be a regular file")
            with os.fdopen(child, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("quote exceeds verified input limit")
            return raw
        finally:
            os.close(child)
    finally:
        os.close(descriptor)


def validate_receipts(plan, contract_id, namespace, receipts):
    from rct_control_plane.intent_contract import IntentContractError, compare, plan_digest
    if not isinstance(receipts, list) or len(receipts) > 50:
        raise IntentContractError("invalid execution receipt list")
    import re
    graph = {node["id"]: node for node in plan["components"]}
    from rct_control_plane.budget_execution import compile_program, registry_for
    program = compile_program(plan)
    handlers = registry_for(plan)
    typed_nodes = {node["id"]: node for node in program["nodes"]}
    outputs: dict[str, dict] = {}
    completed: set[str] = set();previous = "0" * 64;run_version = None
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise IntentContractError("invalid execution receipt")
        data = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        node = graph.get(data.get("component_id"))
        if (node is None or node["id"] in completed or set(node["depends_on"]) - completed
                or data.get("contract_id") != contract_id or data.get("namespace") != namespace
                or data.get("plan_sha256") != plan_digest(plan) or data.get("previous_sha256") != previous
                or data.get("ordinal") != len(completed) + 1 or receipt.get("receipt_sha256") != digest(data)
                or type(data.get("run_version")) is not int or data["run_version"] < 1
                or type(data.get("ordinal")) is not int or type(data.get("recorded_ns")) is not int
                or data["recorded_ns"] < 1 or not isinstance(data.get("output_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", data["output_sha256"])
                or not isinstance(data.get("output"), dict) or data["output_sha256"] != digest(data["output"])):
            raise IntentContractError("execution receipt binding or dependency mismatch")
        if run_version is not None and data["run_version"] != run_version:
            raise IntentContractError("execution receipts belong to different claims")
        typed = typed_nodes[node["id"]]
        handler = handlers[typed["handler"]]
        try:
            normalized = handler.output_model.model_validate(data["output"]).model_dump()
            if digest(normalized) != data["output_sha256"]:
                raise ValueError("receipt output is not canonical typed data")
            if typed["phase"] == "observation":
                binding = plan["semantic_planning"]["quote_evidence"]
                if (normalized["relative_path"] != binding["relative_path"] or normalized["sha256"] != binding["sha256"]
                        or not re.fullmatch(r"[0-9a-f]{64}", normalized["tool_result_sha256"])):
                    raise ValueError("receipt source differs from pinned evidence")
            elif typed["criteria"]:
                if (normalized.get("criterion_id") != typed["criteria"][0]
                        or data["output"].get("satisfied") is not True):
                    raise ValueError("receipt does not verify its criterion")
                criterion = next(c for c in plan["criteria"] if c["id"] == typed["criteria"][0])
                if criterion["kind"] in {"contains", "language", "json_object"}:
                    # Recheck only pure criteria against the recorded report.
                    # Calling the live handler would also evaluate file predicates
                    # against today's filesystem, changing historical semantics.
                    report = outputs[typed["inputs"]["report"]]
                    if compare({"criteria": [criterion]}, json.dumps(report, ensure_ascii=False)):
                        raise ValueError("historical criterion is not satisfied by its recorded report")
            else:
                # Only the fixed, application-owned budget arithmetic/copy
                # handlers are replayed. Never re-read files or run criterion
                # handlers here: these are historical receipts, not a new run.
                payload = {**typed["parameters"], **{port: outputs[parent] for port, parent in typed["inputs"].items()}}
                if handler.run is None:
                    raise ValueError("receipt handler has no implementation")
                expected = handler.run(handler.input_model.model_validate(payload))
                if digest(expected) != data["output_sha256"]:
                    raise ValueError("receipt output differs from its recorded inputs")
        except (ValueError, KeyError, TypeError) as exc:
            raise IntentContractError("execution receipt semantic or type mismatch") from exc
        outputs[node["id"]] = normalized
        run_version = data["run_version"]
        completed.add(node["id"]);previous = receipt["receipt_sha256"]
    return outputs


def validate_stored_execution(contract, contract_id, namespace):
    """Bind the public report/completion projection to validated history.

    No source reread or replay of user effects occurs during status lookup.
    """
    receipts = contract["execution_receipts"]
    outputs = validate_receipts(contract["plan"], contract_id, namespace, receipts)
    report = contract.get("execution_report")
    expected = outputs.get("compare_budget")
    if report is not None and (expected is None or digest(report) != digest(expected)):
        raise ValueError("stored report differs from recorded computation")
    if contract.get("execution_status") == "complete" and (
            len(receipts) != len(contract["plan"]["components"]) or expected is None or report is None):
        raise ValueError("stored completion lacks full receipts/report")


class BudgetPipeline:
    def __init__(self, contract, namespace):
        self.contract = contract;self.namespace = namespace
        self.plan = contract["plan"];self.binding = self.plan["semantic_planning"]["quote_evidence"]
        self.receipts = [];self.report = None;self.error = None
        from rct_control_plane.budget_execution import compile_program, registry_for, validate_executor
        from rct_control_plane.component_execution import ComponentScheduler
        validate_executor(self.plan)
        self.scheduler = ComponentScheduler(compile_program(self.plan), registry_for(self.plan),
            {c["id"] for c in self.plan["criteria"]}, {u["id"]: u["answer"] for u in self.plan["unknowns"]},
            self._record_completion)

    def complete(self, node_id, output):
        self.scheduler.record(node_id, output)

    def _record_completion(self, node_id, output):
        receipt = {"component_id": node_id, "contract_id": self.contract["id"], "namespace": self.namespace,
            "run_version": self.contract["version"], "plan_sha256": self.contract["plan_sha256"],
            "ordinal": len(self.receipts) + 1, "previous_sha256": self.receipts[-1]["receipt_sha256"] if self.receipts else "0" * 64,
            "output": output, "output_sha256": digest(output), "recorded_ns": time.time_ns()}
        receipt["receipt_sha256"] = digest(receipt)
        self.receipts.append(receipt)

    def observe(self, tool, arguments, result):
        if tool != "delentia_read_repo_file" or arguments.get("relative_path") != self.binding["relative_path"]:
            self.error = "unexpected evidence operation";return
        try:
            if not isinstance(result, dict) or result.get("truncated") is not False or result.get("path") != self.binding["relative_path"]:
                raise ValueError("missing, withheld or truncated source")
            raw = result["content_text"].encode("utf-8")
            if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != self.binding["sha256"]:
                raise ValueError("observed source hash differs from plan")
            value = strict_json(raw.decode("utf-8"))
            if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
                raise ValueError("invalid quote version")
            quote = Quote.model_validate(value)
            if quote.total_is_final is not True or Decimal(quote.total) > Decimal("1e15"):
                raise ValueError("quote total/scope unresolved")
            self.scheduler.observe("inspect_sources", {"evidence_status": "observed_bytes", "relative_path": result["path"],
                "sha256": self.binding["sha256"], "tool_result_sha256": digest(result), "quote": quote.model_dump()})
            self.scheduler.drain("compute")
            self.report = self.scheduler.outputs.get("compare_budget")
        except (ValueError, TypeError, KeyError, StopIteration, ValidationError) as exc:
            self.error = str(exc)[:500]

    def decision(self):
        if not self.receipts and self.error is None:
            return {"action": "call_tool", "tool_name": "delentia_read_repo_file",
                "tool_args": {"relative_path": self.binding["relative_path"], "max_bytes": MAX_BYTES, "verified_read": True},
                "reasoning": "Read the pinned quote through the governed tool before dependent computation."}
        return {"action": "finish", "final_answer": json.dumps(self.report if self.error is None else {"unresolved": self.error}, ensure_ascii=False, sort_keys=True),
                "reasoning": "Deterministic decimal verification; no model generation.", "tool_name": None, "tool_args": {}}

    def finish(self, answer, differences):
        if self.error or self.report is None:
            return [{"kind": "verified_budget", "observed": self.error or "missing governed source receipt"}]
        try:
            raw = current_bytes(Path(self.plan["workspace"]), self.binding["relative_path"])
            if hashlib.sha256(raw).hexdigest() != self.binding["sha256"]:
                raise ValueError("source changed after observation")
            authoritative = self.scheduler.outputs.get("compare_budget")
            if authoritative is None or digest(self.report) != digest(authoritative):
                raise ValueError("report differs from completed computation")
            if digest(strict_json(answer)) != digest(authoritative):
                raise ValueError("answer differs from the verified arithmetic report")
            if differences:
                raise ValueError("declared criteria not satisfied")
            self.scheduler.drain("verify")
            self.scheduler.require_complete()
            validate_receipts(self.plan, self.contract["id"], self.namespace, self.receipts)
            if len(self.receipts) != len(self.plan["components"]):
                raise ValueError("not all planned components completed")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return [{"kind": "verified_budget", "observed": str(exc)[:500]}]
        return []
